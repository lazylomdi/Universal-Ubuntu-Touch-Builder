#!/usr/bin/env python3
"""
romforge — custom Android ROM build orchestrator.

Usage:
  python3 romforge.py              # interactive TUI (needs: pip install questionary)
  python3 romforge.py build [opts] # CLI mode (all options explicit)
  python3 romforge.py find  --codename <name> [--vendor <v>] [--kind device|kernel|recovery|tweak]
  python3 romforge.py detect        # detect connected ADB device
  python3 romforge.py versions      # list Android versions
  python3 romforge.py status [--workdir <dir>]  # show pipeline state for a workdir
  python3 romforge.py clear-cache   # clear GitHub API response cache
  python3 romforge.py ut-check [opts] # assess Ubuntu Touch port readiness (offline)

Run `python3 romforge.py build --help` for all CLI build flags.
"""

import argparse
import sys
from pathlib import Path


def _run_build(cfg: dict) -> None:
    """Execute the full build pipeline from a config dict."""
    from build_pipeline import (check_host, repo_sync, clone_tree, load_state,
                           save_state, print_state, launch_background,
                           build_lunch_target)
    from build_pipeline import get_backend
    from customizer import (stage_gapps, stage_assets, stage_boot_animation,
                              enable_initd, fetch_magisk, patch_boot_with_magisk)
    import shutil, subprocess
    from config import VERSIONS

    version  = cfg["version"]
    codename = cfg["codename"]
    workdir  = Path(cfg["workdir"]).expanduser().resolve()
    dry_run  = cfg.get("dry_run", False)
    source   = cfg.get("source", "lineage")
    vinfo    = VERSIONS[version]

    log_path = str(workdir.parent / f"romforge-{version}-{codename}.log")

    # Background launch (must happen before anything else)
    if cfg.get("background") and not cfg.get("_is_background"):
        cli_args = _cfg_to_cli_args(cfg)
        cli_args.append("--_is-background")
        launch_background([sys.executable, __file__, "build"] + cli_args, log_path)
        return

    print(f"\n{'═'*60}")
    print(f"  romforge — Android {version} ({vinfo.viability}) — {codename}")
    print(f"  workdir : {workdir}")
    print(f"{'═'*60}\n")

    if vinfo.viability == "archival":
        print("  ⚠ ARCHIVAL BUILD — expect manual toolchain repair\n")

    # Show and check resume state
    state = load_state(workdir)
    if workdir.exists() and (workdir / ".romforge_state.json").exists():
        print("  Resume state detected:")
        print_state(state)
        print()

    # Host requirement checks
    warnings = check_host()
    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")
        if not cfg.get("force"):
            print("\n  Use --force to proceed anyway.")
            sys.exit(1)
        print()

    # ── Step 1: repo sync ────────────────────────────────────────────────────
    if state["repo_synced"] and not cfg.get("rebuild"):
        print("  [1/5] repo sync — SKIPPED (already done, use --rebuild to force)")
    else:
        print("  [1/5] repo sync")
        ok = repo_sync(
            workdir, version, source,
            use_latest=cfg.get("use_latest_aosp", False),
            jobs=cfg.get("jobs", 4),
            dry_run=dry_run,
        )
        if not ok and not dry_run:
            print("\n  Repo sync failed. The pipeline state has been saved.")
            print("  Re-run the same command to resume from this point.")
            sys.exit(1)
        if not dry_run:
            state["repo_synced"] = True
            save_state(workdir, state)

    # ── Step 2: clone device/vendor/kernel trees ─────────────────────────────
    print("\n  [2/5] tree cloning")
    tree_map = {
        "device":   cfg.get("device_tree_url"),
        "vendor":   cfg.get("vendor_tree_url"),
        "kernel":   cfg.get("kernel_tree_url"),
        "recovery": cfg.get("recovery"),
    }
    for kind, url in tree_map.items():
        if not url:
            continue
        if kind in state["trees_cloned"] and not cfg.get("rebuild"):
            print(f"    {kind} tree — SKIPPED (already cloned)")
            continue
        ok = clone_tree(workdir, kind, url, dry_run=dry_run)
        if ok and not dry_run:
            state["trees_cloned"].append(kind)
            save_state(workdir, state)

    # Clone tweak modules
    for url in (cfg.get("tweaks") or []):
        clone_tree(workdir, "vendor", url, dry_run=dry_run)

    # ── Step 2b: Gerrit patches (specific LineageOS changes onto this tree) ──
    gerrit_patches = cfg.get("gerrit_patch") or []
    if gerrit_patches:
        already = set(state.get("gerrit_patches_applied", []))
        pending = [c for c in gerrit_patches if c not in already or cfg.get("rebuild")]
        if pending:
            print(f"\n  [2b/5] Gerrit patches ({len(pending)} pending)")
            from build_pipeline import apply_gerrit_patches
            ok = apply_gerrit_patches(workdir, pending, dry_run=dry_run)
            if not dry_run:
                state.setdefault("gerrit_patches_applied", [])
                state["gerrit_patches_applied"] = list(set(state["gerrit_patches_applied"]) | set(pending))
                save_state(workdir, state)
            if not ok:
                print("    Some patches failed to apply — see above. "
                      "Resolve conflicts manually, or drop the failing "
                      "change ID and continue without it.")
        else:
            print(f"\n  [2b/5] Gerrit patches — SKIPPED (already applied)")

    # ── Step 3: customizations ───────────────────────────────────────────────
    print("\n  [3/5] customizations")

    if cfg.get("gapps"):
        print("    GApps:")
        stage_gapps(
            workdir, vinfo.api, cfg.get("arch", "arm64"),
            version, cfg.get("gapps_variant"),
            dry_run=dry_run,
        )

    apks = [Path(p) for p in (cfg.get("apks") or [])]
    walls = [Path(p) for p in (cfg.get("wallpapers") or [])]
    if apks or walls:
        print("    Custom assets:")
        stage_assets(workdir, apks, walls, codename, dry_run=dry_run)

    if cfg.get("boot_anim"):
        print("    Boot animation:")
        stage_boot_animation(workdir, Path(cfg["boot_anim"]), dry_run=dry_run)

    if cfg.get("initd"):
        print("    init.d:")
        enable_initd(workdir, codename, vinfo.api, dry_run=dry_run)

    # ── Step 4: build ────────────────────────────────────────────────────────
    print("\n  [4/5] build")
    if state["build_complete"] and not cfg.get("rebuild") and not dry_run:
        print("    SKIPPED — existing build found (use --rebuild to force)")
        zips = state.get("output_zips", [])
        if zips:
            for z in zips:
                print(f"    Flashable ROM: {z}")
    else:
        backend = get_backend(cfg.get("backend", "local"))
        # rom_prefix here is only a fallback for unknown versions —
        # build_lunch_target derives the real prefix (cm_/lineage_/aosp_)
        # per-version internally, since CyanogenMod-era (4-6) builds use
        # "cm", not "lineage".
        lunch_target = cfg.get("lunch_target") or build_lunch_target(
            rom_prefix="lineage" if source == "lineage" else "aosp",
            codename=codename,
            variant="userdebug",
            version=version,
            source=source,
        )

        if cfg.get("backend") == "github-actions":
            from build_pipeline import manifest_url, branch_for
            from config import AOSP_EXTRA_INIT_FLAGS
            backend.run(
                workdir, lunch_target, cfg.get("jobs", 4),
                dry_run=dry_run,
                manifest_url=manifest_url(source, version),
                branch=branch_for(version, source, cfg.get("use_latest_aosp", False)),
                codename=codename,
                version=version,
                init_flags=" ".join(AOSP_EXTRA_INIT_FLAGS) if source == "aosp" else "",
            )
        else:
            ok = backend.run(workdir, lunch_target, cfg.get("jobs", 4), dry_run=dry_run)
            if ok and not dry_run and hasattr(backend, "locate_output"):
                zips = backend.locate_output(workdir, codename)
                if zips:
                    state["build_complete"] = True
                    state["output_zips"] = [str(z) for z in zips]
                    save_state(workdir, state)
                else:
                    print("    ⚠ Build reported success but no .zip found.")
                    print(f"    Check: {workdir}/out/target/product/{codename}/")
            elif not ok and not dry_run:
                sys.exit(1)

    # ── Step 5: root ─────────────────────────────────────────────────────────
    if cfg.get("root"):
        print("\n  [5/5] root (Magisk)")
        magisk_dir = workdir / "magisk"
        apk = fetch_magisk(magisk_dir, dry_run=dry_run)
        if apk:
            boot_img = workdir / "out" / "target" / "product" / codename / "boot.img"
            patch_boot_with_magisk(boot_img, apk, dry_run=dry_run)

    print(f"\n{'═'*60}")
    print("  Done.")
    zips = state.get("output_zips", [])
    for z in zips:
        mb = Path(z).stat().st_size // (1024*1024) if Path(z).exists() else 0
        print(f"  Flashable ROM : {z}  ({mb} MB)")
    print(f"{'═'*60}\n")


def _cfg_to_cli_args(cfg: dict) -> list[str]:
    """Convert a config dict back to CLI args (used for background relaunch)."""
    args = []
    for k, v in cfg.items():
        if k.startswith("_") or v is None or v is False:
            continue
        flag = "--" + k.replace("_", "-")
        if v is True:
            args.append(flag)
        elif isinstance(v, list):
            for item in v:
                args += [flag, str(item)]
        else:
            args += [flag, str(v)]
    return args


def build_cli_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="romforge build",
                                 description="Build a custom Android ROM")
    p.add_argument("--version",      required=True, help="Android version, e.g. 12")
    p.add_argument("--codename",     required=True, help="Device codename, e.g. angler")
    p.add_argument("--vendor",       default="",    help="Vendor hint, e.g. google")
    p.add_argument("--arch",         default="arm64",
                   choices=["arm64","armv7","x86_64","x86"])
    p.add_argument("--source",       default="lineage", choices=["lineage","aosp"])
    p.add_argument("--use-latest-aosp", action="store_true",
                   help="Use android-latest-release branch (AOSP source only)")
    p.add_argument("--workdir",      default="./romforge-src")
    p.add_argument("--backend",      default="local",
                   choices=["local","docker","github-actions"])
    p.add_argument("--jobs",         type=int, default=4)
    p.add_argument("--lunch-target", default=None)
    p.add_argument("--device-tree-url",  default=None)
    p.add_argument("--vendor-tree-url",  default=None)
    p.add_argument("--kernel-tree-url",  default=None)
    p.add_argument("--recovery",         default=None)
    p.add_argument("--gapps",            action="store_true")
    p.add_argument("--gerrit-patch",     action="append", dest="gerrit_patch",
                   default=[], metavar="CHANGE_ID",
                   help="Cherry-pick a specific LineageOS Gerrit change onto "
                        "the synced tree (repeatable). Find change numbers at "
                        "review.lineageos.org. Not a bulk 'apply all Lineage "
                        "patches' option — there's no such artifact; see "
                        "the --source aosp warning for why.")
    p.add_argument("--gapps-variant",    default=None,
                   choices=["core","basic","omni","stock","full"])
    p.add_argument("--root",             action="store_true")
    p.add_argument("--apk",             action="append", dest="apks",    default=[])
    p.add_argument("--wallpaper",       action="append", dest="wallpapers", default=[])
    p.add_argument("--boot-anim",        default=None)
    p.add_argument("--tweak",           action="append", dest="tweaks",  default=[])
    p.add_argument("--initd",            action="store_true")
    p.add_argument("--force",            action="store_true")
    p.add_argument("--rebuild",          action="store_true")
    p.add_argument("--background",       action="store_true",
                   help="Run in tmux/nohup (survives terminal close)")
    p.add_argument("--dry-run",          action="store_true")
    p.add_argument("--_is-background",   action="store_true",
                   dest="_is_background", help=argparse.SUPPRESS)
    return p


def main() -> None:
    # No args → TUI
    if len(sys.argv) == 1:
        try:
            import tui
        except ImportError:
            print("TUI requires questionary: pip install questionary")
            print("Or use: python3 romforge.py build --help")
            sys.exit(1)
        try:
            while True:
                action = tui.main_menu()
                if action is None or action == "Quit":
                    break
                elif action == "Build a ROM":
                    cfg = tui.build_flow()
                    if cfg:
                        _run_build(cfg)
                elif action == "Treble / non-Treble port assistant":
                    import treble_port
                    print("\n  This generates BoardConfig.mk additions, system.prop,")
                    print("  and integration instructions for porting Android 8+ to")
                    print("  32-bit (armv7) or non-Treble 64-bit devices.\n")
                    codename = input("  Device codename: ").strip()
                    vendor   = input("  Vendor: ").strip() or "unknown"
                    arch     = input("  Architecture [armv7/arm64] (default: armv7): ").strip() or "armv7"
                    treble_q = input("  Treble-compatible? [y/N]: ").strip().lower() == "y"
                    soc      = input("  SoC name hint (e.g. 'snapdragon 400', blank to skip): ").strip()
                    cpu_var  = treble_port.suggest_cpu_variant(soc) if soc else (
                               "cortex-a53" if arch == "arm64" else "cortex-a9")
                    api      = int(input(f"  Android API level (default 27): ").strip() or "27")
                    workdir  = Path(input("  Output dir (default ./romforge-src): ").strip()
                                   or "./romforge-src").expanduser().resolve()
                    dry_run  = input("  Dry-run? [Y/n]: ").strip().lower() != "n"

                    detect_q = input("  Read Treble status from connected ADB device? [y/N]: ").strip().lower()
                    if detect_q == "y":
                        status = treble_port.detect_treble_status(codename)
                        treble_port.print_treble_status(status)

                    treble_port.generate_port_files(
                        workdir=workdir, codename=codename, vendor=vendor,
                        arch=arch, treble=treble_q, cpu_variant=cpu_var,
                        android_api=api, dry_run=dry_run,
                    )

                elif action == "Find device trees":
                    import device_resolver
                    codename = input("  Codename: ").strip()
                    vendor   = input("  Vendor (optional): ").strip() or None
                    repos    = device_resolver.search(codename, vendor)
                    device_resolver.print_repos(repos)
                elif action == "List Android versions":
                    from config import VERSIONS
                    print(f"\n  {'Ver':<4} {'API':<5} {'Viability':<10} {'Branch':<18} {'EOL'}")
                    for k, v in VERSIONS.items():
                        print(f"  {k:<4} {v.api:<5} {v.viability:<10} "
                              f"{v.lineage_branch:<18} {'yes' if v.lineage_eol else 'no'}")
                    print()
                elif action == "Detect connected device":
                    import device_resolver
                    info = device_resolver.detect_device()
                    if info:
                        for k, val in info.items():
                            print(f"  {k:12}: {val}")
                    else:
                        print("  No device found (or ADB not installed).")
                elif action == "Settings (GitHub token, cache)":
                    tui.settings_menu()
        except KeyboardInterrupt:
            print("\n  Bye.")
        return

    # Subcommand dispatch
    sub = sys.argv[1]

    if sub == "build":
        p   = build_cli_parser()
        ns  = p.parse_args(sys.argv[2:])
        cfg = vars(ns)
        # Normalise hyphens → underscores from argparse
        cfg = {k.replace("-","_"): v for k, v in cfg.items()}
        _run_build(cfg)

    elif sub == "find":
        import device_resolver
        ap = argparse.ArgumentParser(prog="romforge find")
        ap.add_argument("--codename", required=True)
        ap.add_argument("--vendor",   default=None)
        ap.add_argument("--kind",     default="device",
                        choices=["device","kernel","recovery","tweak"])
        ns = ap.parse_args(sys.argv[2:])
        repos = device_resolver.search(ns.codename, ns.vendor, kind=ns.kind)
        device_resolver.print_repos(repos)

    elif sub == "detect":
        import device_resolver
        info = device_resolver.detect_device()
        if info:
            for k, v in info.items():
                print(f"  {k:12}: {v}")
        else:
            print("  No device found (or ADB not installed).")

    elif sub == "versions":
        from config import VERSIONS
        print(f"\n{'Ver':<5} {'API':<5} {'Viability':<12} {'Branch':<20} {'EOL':<5} Notes")
        print("─" * 80)
        for k, v in VERSIONS.items():
            note = v.note[:45] + "..." if len(v.note) > 45 else v.note
            print(f"{k:<5} {v.api:<5} {v.viability:<12} {v.lineage_branch:<20} "
                  f"{'yes' if v.lineage_eol else 'no':<5} {note}")
        print()

    elif sub == "preflight":
        from preflight import run_preflight
        ap = argparse.ArgumentParser(prog="romforge preflight",
            description="Check build prerequisites without installing tools or starting a build.")
        ap.add_argument("--workdir", default="./romforge-src")
        ap.add_argument("--backend", default="local",
                        choices=["local", "docker", "github-actions"])
        ns = ap.parse_args(sys.argv[2:])
        report = run_preflight(ns.workdir, ns.backend)
        print(f"\nBuild preflight: {report['summary']}")
        print(f"Backend: {report['backend']} · Work directory: {report['workdir']}")
        for item in report["checks"]:
            print(f"  [{item['status']}] {item['name']}: {item['detail']}")
        print("\nThis is a host readiness check, not a device compatibility or bootability guarantee.")
        if not report["ready"]:
            sys.exit(2)

    elif sub == "artifact-report":
        from artifact_manifest import write_artifact_manifest
        ap = argparse.ArgumentParser(prog="romforge artifact-report",
            description="Record artifact metadata and a SHA-256 digest; does not test bootability.")
        ap.add_argument("artifact", help="Path to an existing ROM/image artifact")
        ap.add_argument("--output", default=None, help="Manifest output path (default: next to artifact)")
        ap.add_argument("--codename", default=None)
        ap.add_argument("--android-version", default=None)
        ap.add_argument("--backend", choices=["local", "docker", "github-actions"], default=None)
        ap.add_argument("--jobs", type=int, default=None)
        ap.add_argument("--build-succeeded", action="store_true",
                        help="Record that the build tool reported success; not a boot-test claim")
        ns = ap.parse_args(sys.argv[2:])
        configuration = {"jobs": ns.jobs} if ns.jobs is not None else {}
        manifest = write_artifact_manifest(
            ns.artifact, ns.output, codename=ns.codename,
            android_version=ns.android_version, backend=ns.backend,
            configuration=configuration, build_succeeded=ns.build_succeeded)
        print(f"Artifact manifest written: {manifest}")
        print("The manifest records a SHA-256 digest; it does not verify publisher authenticity or bootability.")

    elif sub == "status":
        from build_pipeline import load_state, print_state
        ap = argparse.ArgumentParser(prog="romforge status")
        ap.add_argument("--workdir", default="./romforge-src")
        ns = ap.parse_args(sys.argv[2:])
        wd = Path(ns.workdir).expanduser().resolve()
        state = load_state(wd)
        print(f"\n  Pipeline state for: {wd}")
        print_state(state)
        print()

    elif sub == "port":
        # Treble / non-Treble porting assistant
        import treble_port
        ap = argparse.ArgumentParser(prog="romforge port",
            description="Generate BoardConfig.mk/system.prop patches for porting "
                        "Android 8+ to 32-bit or non-Treble 64-bit devices.")
        ap.add_argument("--codename",    required=True)
        ap.add_argument("--vendor",      default="unknown")
        ap.add_argument("--arch",        choices=["armv7", "arm64"], required=True)
        ap.add_argument("--treble",      action="store_true",
                        help="Generate Treble-compatible config (64-bit with /vendor "
                             "partition). Default: non-Treble.")
        ap.add_argument("--cpu-variant", default=None,
                        help="CPU core variant e.g. cortex-a9, cortex-a53, krait, kryo. "
                             "Used in BoardConfig and system.prop.")
        ap.add_argument("--soc",         default=None,
                        help="SoC name hint for auto-detecting CPU variant "
                             "(e.g. 'snapdragon 800', 'exynos 5', 'mt6580').")
        ap.add_argument("--api",         type=int, default=27,
                        help="Android API level of the ROM you are building (default: 27).")
        ap.add_argument("--workdir",     default="./romforge-src")
        ap.add_argument("--detect",      action="store_true",
                        help="Read Treble status from a connected ADB device before generating.")
        ap.add_argument("--dry-run",     action="store_true")
        ns = ap.parse_args(sys.argv[2:])

        if ns.detect:
            print("\n  Reading Treble status from connected device...")
            status = treble_port.detect_treble_status(ns.codename)
            treble_port.print_treble_status(status)

        cpu_variant = ns.cpu_variant
        if not cpu_variant and ns.soc:
            cpu_variant = treble_port.suggest_cpu_variant(ns.soc)
            print(f"  Auto-detected CPU variant from SOC hint: {cpu_variant}")
        if not cpu_variant:
            cpu_variant = "cortex-a53" if ns.arch == "arm64" else "cortex-a9"
            print(f"  No --cpu-variant given, using default: {cpu_variant}")

        workdir = Path(ns.workdir).expanduser().resolve()
        files = treble_port.generate_port_files(
            workdir=workdir,
            codename=ns.codename,
            vendor=ns.vendor,
            arch=ns.arch,
            treble=ns.treble,
            cpu_variant=cpu_variant,
            android_api=ns.api,
            dry_run=ns.dry_run,
        )
        if not ns.dry_run:
            print(f"\n  Generated {len(files)} file(s) in {workdir / 'treble_port'}/")
            print(f"  Read PORTING_README.txt before merging anything into your device tree.")

    elif sub == "ut-check":
        import ut_check
        raise SystemExit(ut_check.main(sys.argv[2:]))

    elif sub == "clear-cache":
        import github_client
        n = github_client.clear_cache()
        print(f"  Cleared {n} cached API responses from {github_client._CACHE_DIR}")

    else:
        print(f"Unknown subcommand '{sub}'. Run without args for TUI, or --help.")
        print("Subcommands: build, port, find, detect, versions, status, clear-cache, ut-check")
        sys.exit(1)


if __name__ == "__main__":
    main()
