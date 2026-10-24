#!/usr/bin/env python3
"""
<<<<<<< HEAD:romforge.py
romforge — custom Android ROM build orchestrator.
=======
main.py
>>>>>>> 7c5254ed76103d9d10fe40261c9f03411338ffd6:main.py

Usage:
  python3 romforge.py              # interactive TUI (needs: pip install questionary)
  python3 romforge.py build [opts] # CLI mode (all options explicit)
  python3 romforge.py find  --codename <name> [--vendor <v>] [--kind device|kernel|recovery|tweak]
  python3 romforge.py detect        # detect connected ADB device
  python3 romforge.py versions      # list Android versions
  python3 romforge.py status [--workdir <dir>]  # show pipeline state for a workdir
  python3 romforge.py clear-cache   # clear GitHub API response cache

Run `python3 romforge.py build --help` for all CLI build flags.
"""
import argparse
import os
import shutil
import sys

from pathlib import Path

<<<<<<< HEAD:romforge.py
=======
from config import ANDROID_VERSIONS, ARCHES, NIKGAPPS_VARIANTS
from device_resolver import (detect_connected_device, search_device_trees,
                               search_kernel_trees, search_tweak_modules, print_candidates)
from source_manager import SourceManager
from builder import get_backend
from customizer import (stage_gapps, stage_custom_assets, stage_tweak_modules,
                          stage_boot_animation, enable_initd_support,
                          surface_radio_notes, surface_selinux_notes,
                          search_recovery_trees,
                          fetch_latest_magisk, patch_boot_image_with_magisk)
>>>>>>> 7c5254ed76103d9d10fe40261c9f03411338ffd6:main.py

def _run_build(cfg: dict) -> None:
    """Execute the full build pipeline from a config dict."""
    from pipeline import (check_host, repo_sync, clone_tree, load_state,
                           save_state, print_state, launch_background)
    from backends import get_backend
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

<<<<<<< HEAD:romforge.py
    # Host requirement checks
    warnings = check_host()
    if warnings:
        for w in warnings:
            print(f"  ⚠ {w}")
        if not cfg.get("force"):
            print("\n  Use --force to proceed anyway.")
=======
    # --- Build a ROM ---
    version = questionary.select(
        "Android version to build:",
        choices=[f"{v} (API {info.api_level}, {info.viability})"
                  for v, info in ANDROID_VERSIONS.items()],
    ).ask()
    if version is None:
        return
    version = version.split(" ")[0]
    info = ANDROID_VERSIONS[version]
    if info.viability == "archival-only":
        proceed = questionary.confirm(
            f"Android {version} is rated archival-only -- expect manual "
            f"toolchain repair regardless. Continue?", default=False).ask()
        if not proceed:
            return

    source = questionary.select(
        "Source to build from:",
        choices=["lineage (most device trees target this)", "aosp (raw AOSP)"],
    ).ask()
    if source is None:
        return
    source = "lineage" if source.startswith("lineage") else "aosp"

    use_latest_aosp = False
    if source == "aosp":
        use_latest_aosp = questionary.confirm(
            "Use Google's current rolling android-latest-release branch "
            "instead of the historical numbered tag for this version?",
            default=True).ask()

    detected = detect_connected_device()
    codename = None
    vendor = None
    if detected:
        use_detected = questionary.confirm(
            f"Detected connected device '{detected['codename']}' "
            f"({detected['vendor']}, {detected['arch']}). Use it?", default=True).ask()
        if use_detected:
            codename = detected["codename"]
            vendor = detected["vendor"]
            arch = detected["arch"]
    if codename is None:
        codename = questionary.text("Device codename:").ask()
        if not codename:
            return
        vendor = questionary.text("Vendor hint (optional):", default="").ask() or None
        arch = questionary.select("Device architecture:", choices=list(ARCHES.keys())).ask()
        if arch is None:
            return

    backend = questionary.select(
        "Build backend:",
        choices=["local", "docker", "github-actions"],
    ).ask()
    if backend is None:
        return

    extras = questionary.checkbox(
        "Optional add-ons (space to toggle, enter to confirm):",
        choices=["Stage GApps", "Patch root (Magisk)", "Select a kernel tree",
                 "Tweak/mod modules", "init.d support (legacy, mostly Android 4-9)"],
    ).ask()
    if extras is None:
        extras = []
    gapps = "Stage GApps" in extras
    root = "Patch root (Magisk)" in extras
    kernel = "Select a kernel tree" in extras
    want_tweaks = "Tweak/mod modules" in extras
    initd = "init.d support (legacy, mostly Android 4-9)" in extras

    gapps_variant = None
    if gapps:
        choices = [f"{name} -- {desc}" for name, desc in NIKGAPPS_VARIANTS.items()]
        pick = questionary.select("GApps variant:", choices=choices).ask()
        if pick:
            gapps_variant = pick.split(" -- ")[0]

    tweak_queries = []
    if want_tweaks:
        print("Enter tweak/mod search terms one at a time (e.g. 'viper4android', "
              "'adaway'). Leave blank to stop.")
        while True:
            q = questionary.text("Tweak search term (blank to finish):", default="").ask()
            if not q:
                break
            tweak_queries.append(q)

    apks, wallpapers = [], []
    if questionary.confirm("Add a custom APK?", default=False).ask():
        apk_path = questionary.path("Path to APK:").ask()
        if apk_path:
            apks.append(apk_path)
    if questionary.confirm("Add a custom wallpaper?", default=False).ask():
        wp_path = questionary.path("Path to wallpaper image:").ask()
        if wp_path:
            wallpapers.append(wp_path)

    jobs_str = questionary.text("Parallel build jobs:", default="4").ask()
    try:
        jobs = int(jobs_str)
    except (TypeError, ValueError):
        jobs = 4

    dry_run = questionary.confirm(
        "Dry-run first (recommended -- prints every command without "
        "running anything)?", default=True).ask()

    workdir = questionary.text("Source working directory:", default="./romforge-src").ask()

    # Pre-check host requirements here too, so the TUI can offer --force
    # interactively instead of silently failing after a long Q&A session.
    probe = SourceManager(Path(workdir).expanduser(), source=source)
    host_warnings = probe.check_host_requirements()
    force = False
    if host_warnings:
        print("\nHost requirement warnings:")
        for w in host_warnings:
            print(f"  - {w}")
        force = questionary.confirm(
            "Proceed anyway despite the warnings above?", default=False).ask()
        if not force:
            print("Stopping -- resolve the warnings above and try again.")
            return

    ns = argparse.Namespace(
        version=version, source=source, use_latest_aosp=use_latest_aosp,
        codename=codename, vendor=vendor, arch=arch, workdir=workdir,
        backend=backend, lunch_target=None, jobs=jobs, gapps=gapps,
        gapps_variant=gapps_variant, root=root, kernel=kernel,
        tweak=tweak_queries or None, initd=initd,
        apk=apks or None, wallpaper=wallpapers or None, skip_device_tree=False,
        auto_select=False, force=force, dry_run=bool(dry_run),
        background=False, rebuild=False, boot_animation=None,
        recovery=None, is_background=False,
    )
    cmd_build(ns)


def cmd_list_versions(_args):
    print(f"{'Version':<8}{'API':<5}{'Viability':<16}{'Lineage branch':<18}{'Notes'}")
    for v, info in ANDROID_VERSIONS.items():
        print(f"{v:<8}{info.api_level:<5}{info.viability:<16}"
              f"{(info.lineage_branch or '-'):<18}{info.notes[:60]}")
    print("\nArches:")
    for name, a in ARCHES.items():
        print(f"  {name:<8} bitness={a['bitness']} tier={a['tier']} common for: {a['common_for']}")


def cmd_detect_device(_args):
    info = detect_connected_device()
    if info is None:
        print("No connected device found (or adb not installed). "
              "Connect a device with USB debugging enabled and try again.")
        return
    print("Detected device:")
    for k, v in info.items():
        print(f"  {k}: {v}")


def cmd_find_device(args):
    print(f"Searching GitHub for device trees matching '{args.codename}'"
          + (f" (vendor hint: {args.vendor})" if args.vendor else "") + " ...")
    candidates = search_device_trees(args.codename, vendor_hint=args.vendor)
    print_candidates(candidates)
    if candidates:
        print("\nNote: review each result before cloning -- stars/recency are "
              "a starting filter, not a trust guarantee. Prefer LineageOS/"
              "TheMuppets org results when available.")


def _pick_repo_interactively(candidates: list, label: str, auto_select: bool) -> object | None:
    """
    Shared "show exact matches, let the person choose" flow used for
    device trees AND kernel trees (the same UX, just a different kind of
    repo). Returns the chosen RepoCandidate, or None if skipped/unavailable.
    Never falls back to silently picking the top result unless
    auto_select=True -- see the d2att incident in earlier testing for why.
    """
    exact = [c for c in candidates if c.exact_match]
    interactive = questionary is not None and sys.stdin.isatty()

    if not candidates:
        print(f"  No {label} candidates found.")
        return None
    if not exact:
        print(f"  No EXACT match found among {label} candidates -- only "
              f"partial/substring matches. Refusing to auto-select.")
        return None
    if auto_select:
        choice = next((c for c in exact if c.vendor_match), exact[0])
        print(f"  --auto-select: picked {choice.full_name} for {label} "
              f"(highest-ranked exact match). Review this before trusting "
              f"the build -- {len(exact)} exact match(es) were found in total.")
        return choice
    if interactive:
        labels = [f"{c.full_name}  (★{c.stars}, pushed {c.pushed_at[:10]})" for c in exact]
        choice = questionary.select(
            f"{len(exact)} exact {label} match(es) found -- pick one:",
            choices=labels + [f"Skip -- I'll provide the {label} myself"],
        ).ask()
        if choice and not choice.startswith("Skip"):
            return exact[labels.index(choice)]
        return None
    print(f"  Multiple exact {label} matches found but no TTY/questionary "
          f"available to prompt for a choice. Re-run interactively, or "
          f"pass --auto-select to take the top-ranked match without prompting.")
    return None


def _launch_background(args_list: list[str], workdir: str, log_path: str) -> None:
    """
    Re-launch this exact command in the background so it survives terminal
    close / SSH disconnect / screen lock. Tries tmux first (preferred --
    lets you reattach and see the TUI/output again later), falls back to
    nohup (output goes to log file only).

    Verified approach:
      tmux new-session -d -s romforge '<cmd>' 2>/dev/null
        -d  = detached (don't attach immediately)
        -s  = session name (so you can `tmux attach -t romforge` later)
      nohup python3 romforge.py ... > <logfile> 2>&1 &
        nohup = immune to SIGHUP when terminal closes
        &     = background immediately
    Source: verified against tmux docs + nohup/disown Ubuntu 2026 guide.
    """
    import shlex
    cmd = " ".join(shlex.quote(a) for a in args_list)
    log = log_path

    if shutil.which("tmux"):
        session = "romforge"
        # Kill any existing stale romforge session silently
        subprocess.run(["tmux", "kill-session", "-t", session],
                       capture_output=True)
        full_cmd = f"{cmd} 2>&1 | tee {shlex.quote(log)}"
        subprocess.run(["tmux", "new-session", "-d", "-s", session, full_cmd])
        print(f"  Launched in tmux session '{session}'.")
        print(f"  Reattach at any time with:  tmux attach -t {session}")
        print(f"  Output is also logged to:   {log}")
        print(f"  Kill the build with:        tmux kill-session -t {session}")
    else:
        import os
        bg_cmd = f"nohup {cmd} > {shlex.quote(log)} 2>&1 &"
        os.system(bg_cmd)
        print(f"  Launched with nohup (tmux not found -- install it for a "
              f"reattachable session: sudo apt install tmux).")
        print(f"  Output is logged to: {log}")
        print(f"  Monitor progress:    tail -f {log}")
        print(f"  Find the PID with:   pgrep -f 'romforge.py'")
    sys.exit(0)  # parent exits; child runs detached


def cmd_build(args):
    if args.version not in ANDROID_VERSIONS:
        print(f"Unknown version '{args.version}'. Run `list-versions` to see options.")
        sys.exit(1)
    info = ANDROID_VERSIONS[args.version]
    workdir = Path(args.workdir).expanduser().resolve()
    log_path = str(workdir.parent / f"romforge-build-{args.version}.log")

    # Background launch -- re-run this exact command detached from terminal
    # so it survives closing the window, SSH disconnect, or screen lock.
    # Must happen BEFORE anything long-running starts.
    if getattr(args, "background", False) and not getattr(args, "is_background", False):
        rebuild = [sys.executable] + sys.argv[:]
        rebuild = [a for a in rebuild if a not in ("--background",)]
        rebuild.append("--is-background")
        _launch_background(rebuild, str(workdir), log_path)
        return

    print(f"=== ROMForge build: Android {args.version} ({info.viability}) ===")
    if info.viability == "archival-only":
        print("  WARNING: this version is rated archival-only. Expect manual "
              "toolchain/dependency repair regardless of how this proceeds.")
    surface_selinux_notes(info.viability)
    surface_radio_notes()

    sm = SourceManager(workdir, source=args.source,
                        use_latest_aosp=getattr(args, "use_latest_aosp", False))

    # Resume detection: check what's already done in the workdir once,
    # then use that single snapshot throughout cmd_build so we're not
    # making multiple detect_state() calls that could give different results.
    build_state = sm.detect_state() if workdir.exists() else {
        "repo_initialized": False, "source_synced": False,
        "device_tree": False, "vendor_tree": False,
        "kernel_tree": False, "build_complete": False,
    }
    if workdir.exists():
        sm.print_state(build_state)
        if build_state["source_synced"]:
            print("  Source tree already synced -- skipping repo init/sync (resume mode).")
        if build_state["build_complete"] and not getattr(args, "rebuild", False):
            print("  Existing build artifact found. Use --rebuild to force a new build.")

    warnings = sm.check_host_requirements()
    for w in warnings:
        print(f"  [warning] {w}")
    if warnings and not args.force:
        print("  Resolve the warnings above, or re-run with --force to proceed anyway.")
        sys.exit(1)

    # 1. Device tree resolution (search + optional ADB auto-detect)
    codename = args.codename
    vendor = args.vendor
    if codename is None:
        detected = detect_connected_device()
        if detected:
            codename = detected["codename"]
            vendor = vendor or detected["vendor"]
            print(f"  Auto-detected connected device: {codename} ({vendor})")
        else:
            print("  No --codename given and no connected device detected. "
                  "Pass --codename explicitly.")
>>>>>>> 7c5254ed76103d9d10fe40261c9f03411338ffd6:main.py
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

<<<<<<< HEAD:romforge.py
    # Clone tweak modules
    for url in (cfg.get("tweaks") or []):
        clone_tree(workdir, "vendor", url, dry_run=dry_run)
=======
    # 2. Source sync (skipped in resume mode if tree already present)
    if build_state.get("source_synced") and not getattr(args, "rebuild", False):
        print(f"\n--- Syncing source ({args.source}): SKIPPED (already synced) ---")
    else:
        print(f"\n--- Syncing source ({args.source}) ---")
        if not sm.init_and_sync(args.version, jobs=args.jobs, dry_run=args.dry_run):
            print("  Source sync failed -- see message above. Stopping.")
            sys.exit(1)
>>>>>>> 7c5254ed76103d9d10fe40261c9f03411338ffd6:main.py

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

<<<<<<< HEAD:romforge.py
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
=======
    if getattr(args, "boot_animation", None):
        print("\n--- Staging boot animation ---")
        stage_boot_animation(workdir, Path(args.boot_animation), dry_run=args.dry_run)

    if getattr(args, "recovery", None):
        print(f"\n--- Finding {args.recovery} recovery tree for '{codename}' ---")
        recovery_candidates = search_recovery_trees(codename, vendor, args.recovery)
        print_candidates(recovery_candidates)
        recovery_repo = _pick_repo_interactively(recovery_candidates, "recovery tree", args.auto_select)
        if recovery_repo is not None:
            print(f"  Selected recovery: {recovery_repo.full_name}")
            clone_urls["recovery"] = recovery_repo.clone_url
            sm.clone_device_trees({"recovery": recovery_repo.clone_url}, dry_run=args.dry_run)
        else:
            print("  No recovery tree selected -- ROM will use the default recovery.")

    # 4. Build (skip if existing artifact found and --rebuild not set)
    if build_state.get("build_complete") and not getattr(args, "rebuild", False) and not args.dry_run:
        print(f"\n--- Building: SKIPPED (existing artifact found; use --rebuild to force) ---")
        output_zip = get_backend("local").locate_output(workdir, codename) if args.backend == "local" else None
        if output_zip:
            print(f"\n=== Done ===\nFlashable ROM: {output_zip}")
        return
    print(f"\n--- Building ({args.backend} backend) ---")
    lunch_target = args.lunch_target or f"lineage_{codename}-userdebug"
    backend = get_backend(args.backend)
    if args.backend == "github-actions":
        from backends_remote import GithubActionsBuildBackend
        gh = backend  # type: GithubActionsBuildBackend
        gh.write_workflow(workdir, sm.manifest_url(), sm.branch_for(args.version),
                           lunch_target, dry_run=args.dry_run)
        backend.run_build(workdir, lunch_target, args.jobs, dry_run=args.dry_run)
        return
    elif args.backend == "docker":
        built = backend.run_build(workdir, lunch_target, args.jobs, dry_run=args.dry_run)
>>>>>>> 7c5254ed76103d9d10fe40261c9f03411338ffd6:main.py
    else:
        backend = get_backend(cfg.get("backend", "local"))
        lunch_target = cfg.get("lunch_target") or f"lineage_{codename}-userdebug"

        if cfg.get("backend") == "github-actions":
            from pipeline import manifest_url, branch_for
            from config import AOSP_EXTRA_INIT_FLAGS
            backend.run(
                workdir, lunch_target, cfg.get("jobs", 4),
                dry_run=dry_run,
                manifest_url=manifest_url(source),
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

<<<<<<< HEAD:romforge.py
=======
    sub.add_parser("list-versions", help="List supported Android versions and arches").set_defaults(func=cmd_list_versions)

    sub.add_parser("tui", help="Interactive arrow-key menu mode (needs questionary)").set_defaults(func=lambda _args: run_tui())

    sub.add_parser("detect-device", help="Read codename/arch from a connected ADB device").set_defaults(func=cmd_detect_device)

    pf = sub.add_parser("find-device", help="Search GitHub for device trees by codename")
    pf.add_argument("--codename", required=True)
    pf.add_argument("--vendor", default=None)
    pf.set_defaults(func=cmd_find_device)

    pb = sub.add_parser("build", help="Run the full pipeline")
    pb.add_argument("--version", required=True, help="Android major version, e.g. 12")
    pb.add_argument("--source", choices=["lineage", "aosp"], default="lineage")
    pb.add_argument("--use-latest-aosp", action="store_true",
                     help="With --source aosp, use Google's current rolling "
                          "android-latest-release branch instead of a "
                          "historical numbered tag (see config.py notes)")
    pb.add_argument("--codename", default=None, help="Device codename (omit to auto-detect via ADB)")
    pb.add_argument("--vendor", default=None, help="Vendor hint, e.g. google, samsung")
    pb.add_argument("--arch", choices=list(ARCHES.keys()), default="arm64")
    pb.add_argument("--workdir", default="./romforge-src")
    pb.add_argument("--backend", choices=["local", "docker", "github-actions"], default="local")
    pb.add_argument("--lunch-target", default=None)
    pb.add_argument("--jobs", type=int, default=4)
    pb.add_argument("--gapps", action="store_true", help="Stage GApps for this version/arch")
    pb.add_argument("--gapps-variant", choices=list(NIKGAPPS_VARIANTS.keys()), default=None,
                     help="NikGapps variant (core/basic/omni/stock/full); requires --gapps")
    pb.add_argument("--root", action="store_true", help="Patch output boot.img with Magisk")
    pb.add_argument("--apk", action="append", help="Path to a custom APK to bundle (repeatable)")
    pb.add_argument("--wallpaper", action="append", help="Path to a custom wallpaper image (repeatable)")
    pb.add_argument("--kernel", action="store_true",
                     help="Search for and select a kernel tree separately from the device tree")
    pb.add_argument("--tweak", action="append", default=None,
                     help="Search term for a Magisk/KernelSU tweak module to stage (repeatable, "
                          "e.g. --tweak viper4android --tweak adaway)")
    pb.add_argument("--initd", action="store_true",
                     help="Create /system/etc/init.d structure + setup notes (legacy, mostly "
                          "relevant to Android 4-9-era CM/early-Lineage builds)")
    pb.add_argument("--skip-device-tree", action="store_true", help="Skip auto device tree clone")
    pb.add_argument("--auto-select", action="store_true",
                     help="Non-interactive: pick the top-ranked exact device "
                          "tree match without prompting (for scripted runs)")
    pb.add_argument("--force", action="store_true", help="Proceed despite host requirement warnings")
    pb.add_argument("--dry-run", action="store_true", help="Print commands without executing them")
    pb.add_argument("--background", action="store_true",
                     help="Run the build in a detached tmux session (or nohup fallback) "
                          "so it survives terminal close / SSH disconnect. "
                          "Reattach with: tmux attach -t romforge")
    pb.add_argument("--rebuild", action="store_true",
                     help="Force a fresh build even if an existing artifact is detected "
                          "in the workdir (resume mode skips the build by default if one exists)")
    pb.add_argument("--boot-animation", default=None, metavar="ZIP",
                     help="Path to a bootanimation.zip to embed (desc.txt + part*/ PNG frames)")
    pb.add_argument("--recovery", choices=["twrp", "orangefox", "skyhawk"], default=None,
                     help="Search for and select a custom recovery image tree to build alongside the ROM")
    pb.add_argument("--is-background", action="store_true",
                     help=argparse.SUPPRESS)  # internal sentinel, not shown in --help
    pb.set_defaults(func=cmd_build)
>>>>>>> 7c5254ed76103d9d10fe40261c9f03411338ffd6:main.py

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

    elif sub == "status":
        from pipeline import load_state, print_state
        ap = argparse.ArgumentParser(prog="romforge status")
        ap.add_argument("--workdir", default="./romforge-src")
        ns = ap.parse_args(sys.argv[2:])
        wd = Path(ns.workdir).expanduser().resolve()
        state = load_state(wd)
        print(f"\n  Pipeline state for: {wd}")
        print_state(state)
        print()

    elif sub == "clear-cache":
        import github_client
        n = github_client.clear_cache()
        print(f"  Cleared {n} cached API responses from {github_client._CACHE_DIR}")

    else:
        print(f"Unknown subcommand '{sub}'. Run without args for TUI, or --help.")
        print("Subcommands: build, find, detect, versions, status, clear-cache")
        sys.exit(1)


if __name__ == "__main__":
    main()
