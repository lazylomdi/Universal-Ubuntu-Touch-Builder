"""
tui.py — interactive TUI using questionary.

This file contains ONLY the UI logic: asking questions and collecting
a config dict. No pipeline logic lives here. The config dict is passed
to run_build() in romforge.py which handles the actual work.

Structure:
  main_menu()   — top-level: what do you want to do?
  build_flow()  — walk through build options, return config dict
  settings()    — GitHub token, cache management
"""

try:
    import questionary
    from questionary import Style
    HAS_Q = True
except ImportError:
    HAS_Q = False

from config import VERSIONS, ARCHS, NIKGAPPS_VARIANTS
import github_client
import device_resolver


STYLE = None
if HAS_Q:
    STYLE = Style([
        ("qmark",       "fg:#00d7ff bold"),
        ("question",    "bold"),
        ("answer",      "fg:#00ff87 bold"),
        ("pointer",     "fg:#00d7ff bold"),
        ("highlighted", "fg:#00d7ff bold"),
        ("selected",    "fg:#00ff87"),
        ("separator",   "fg:#444444"),
        ("instruction", "fg:#888888"),
        ("text",        ""),
        ("disabled",    "fg:#444444 italic"),
    ])


def _q(widget, **kwargs):
    """Call questionary widget with shared style, handle Ctrl-C gracefully."""
    try:
        result = widget(**kwargs, style=STYLE).ask()
        if result is None:
            raise KeyboardInterrupt
        return result
    except KeyboardInterrupt:
        raise


def main_menu() -> str | None:
    if not HAS_Q:
        print("TUI requires questionary: pip install questionary")
        return None
    return _q(questionary.select, message="What do you want to do?",
              choices=[
                  "Build a ROM",
                  "Treble / non-Treble port assistant",
                  "Find device trees",
                  "List Android versions",
                  "Detect connected device",
                  "Settings (GitHub token, cache)",
                  "Quit",
              ])


def settings_menu() -> None:
    choice = _q(questionary.select, message="Settings",
                choices=[
                    "Set GitHub token",
                    "Show token status",
                    "Clear API cache",
                    "Back",
                ])
    if choice == "Set GitHub token":
        print("\n  A GitHub personal access token (PAT) raises the API limit")
        print("  from 60 req/hr to 5,000 req/hr. No scopes needed — public")
        print("  repo access only. Create one at: github.com/settings/tokens")
        token = _q(questionary.password, message="Paste token (input hidden):")
        if token.strip():
            github_client.set_token(token.strip())
            print(f"  Token saved to {github_client._TOKEN_FILE}")
        else:
            print("  No token entered, nothing changed.")
    elif choice == "Show token status":
        print(f"  {github_client.token_status()}")
    elif choice == "Clear API cache":
        n = github_client.clear_cache()
        print(f"  Cleared {n} cached API responses.")


def _pick_repo(repos: list, label: str) -> object | None:
    """Show repos and let the user pick one or skip."""
    if not repos:
        print(f"  No {label} results. Check token or try a different codename.")
        return None
    exact = [r for r in repos if r.exact_match]
    pool  = exact if exact else repos
    choices = [
        f"{r.full_name:<55} ★{r.stars:<5} {r.pushed}"
        + (" [exact]" if r.exact_match else " [PARTIAL]")
        for r in pool
    ]
    choices.append("Skip — provide manually")
    pick = _q(questionary.select, message=f"Select {label}:", choices=choices)
    if pick.startswith("Skip"):
        return None
    idx = choices.index(pick)
    return pool[idx]


def build_flow() -> dict | None:
    """Walk through all build options and return a config dict."""
    cfg = {}

    # ── Android version ──────────────────────────────────────────────────────
    ver_choices = [
        f"{k}  (API {v.api}, {v.viability})"
        + ("  [EOL]" if v.lineage_eol else "")
        for k, v in VERSIONS.items()
    ]
    pick = _q(questionary.select, message="Android version:", choices=ver_choices)
    cfg["version"] = pick.split()[0]
    vinfo = VERSIONS[cfg["version"]]

    if vinfo.viability == "archival":
        ok = _q(questionary.confirm,
                message=f"Android {cfg['version']} is rated archival — expect manual "
                        f"toolchain repair. Continue?", default=False)
        if not ok:
            return None

    # ── Source ───────────────────────────────────────────────────────────────
    cfg["source"] = _q(questionary.select, message="Source:",
                       choices=["lineage  (recommended — most device trees target this)",
                                "aosp     (raw AOSP)"])
    cfg["source"] = cfg["source"].split()[0]

    cfg["use_latest_aosp"] = False
    if cfg["source"] == "aosp":
        cfg["use_latest_aosp"] = _q(questionary.confirm,
            message="Use rolling android-latest-release branch? "
                    "(Recommended for fresh builds; unchecked = pinned historical tag)",
            default=True)

    # ── Device ───────────────────────────────────────────────────────────────
    detected = device_resolver.detect_device()
    if detected:
        use = _q(questionary.confirm,
                 message=f"Detected {detected['codename']} ({detected['vendor']}, "
                         f"{detected['arch']}). Use it?", default=True)
        if use:
            cfg["codename"] = detected["codename"]
            cfg["vendor"]   = detected["vendor"]
            cfg["arch"]     = detected["arch"]

    if "codename" not in cfg:
        cfg["codename"] = _q(questionary.text, message="Device codename (e.g. angler):")
        cfg["vendor"]   = _q(questionary.text, message="Vendor (e.g. google):") or ""
        cfg["arch"]     = _q(questionary.select, message="Architecture:", choices=ARCHS)

    # ── Device tree search ───────────────────────────────────────────────────
    print(f"\n  Searching for device trees for '{cfg['codename']}'...")
    repos = device_resolver.search(cfg["codename"], cfg.get("vendor"), kind="device")
    device_resolver.print_repos(repos)
    repo = _pick_repo(repos, "device tree")
    cfg["device_tree_url"] = repo.clone_url if repo else None

    # Vendor tree (auto-searched from same results)
    vendor_repos = [r for r in repos if r.kind == "vendor"]
    cfg["vendor_tree_url"] = vendor_repos[0].clone_url if vendor_repos else None
    if cfg["vendor_tree_url"]:
        print(f"  Auto-selected vendor tree: {vendor_repos[0].full_name}")

    # ── Kernel tree (optional) ───────────────────────────────────────────────
    want_kernel = _q(questionary.confirm,
                     message="Search for a separate kernel tree?", default=False)
    cfg["kernel_tree_url"] = None
    if want_kernel:
        print(f"  Searching kernel trees for '{cfg['codename']}'...")
        krepos = device_resolver.search(cfg["codename"], cfg.get("vendor"), kind="kernel")
        device_resolver.print_repos(krepos)
        krepo = _pick_repo(krepos, "kernel tree")
        cfg["kernel_tree_url"] = krepo.clone_url if krepo else None

    # ── GApps ────────────────────────────────────────────────────────────────
    cfg["gapps"] = False
    cfg["gapps_variant"] = None
    want_gapps = _q(questionary.confirm, message="Include GApps?", default=True)
    if want_gapps:
        cfg["gapps"] = True
        if vinfo.api >= 29:
            var_choices = [f"{k} — {v}" for k, v in NIKGAPPS_VARIANTS.items()]
            pick = _q(questionary.select, message="NikGapps variant:", choices=var_choices)
            cfg["gapps_variant"] = pick.split(" — ")[0]

    # ── Custom assets ─────────────────────────────────────────────────────────
    cfg["apks"]       = []
    cfg["wallpapers"] = []
    cfg["boot_anim"]  = None

    if _q(questionary.confirm, message="Add custom APKs or wallpapers?", default=False):
        while True:
            p = _q(questionary.path, message="APK path (blank to stop):")
            if not p:
                break
            cfg["apks"].append(p)
        while True:
            p = _q(questionary.path, message="Wallpaper path (blank to stop):")
            if not p:
                break
            cfg["wallpapers"].append(p)

    if _q(questionary.confirm, message="Add custom boot animation?", default=False):
        cfg["boot_anim"] = _q(questionary.path, message="bootanimation.zip path:")

    # ── Tweaks ────────────────────────────────────────────────────────────────
    cfg["tweaks"] = []
    if _q(questionary.confirm, message="Search for Magisk/KernelSU tweak modules?",
           default=False):
        while True:
            q = _q(questionary.text,
                   message="Search term (e.g. 'viper4android', blank to stop):")
            if not q:
                break
            print(f"  Searching for '{q}'...")
            results = device_resolver.search(q, kind="tweak")
            device_resolver.print_repos(results)
            repo = _pick_repo(results, f"module for '{q}'")
            if repo:
                cfg["tweaks"].append(repo.clone_url)

    # ── Root ─────────────────────────────────────────────────────────────────
    cfg["root"] = _q(questionary.confirm,
                     message="Patch boot.img with Magisk (root)?", default=False)

    # ── init.d ───────────────────────────────────────────────────────────────
    cfg["initd"] = False
    if vinfo.api <= 28:
        cfg["initd"] = _q(questionary.confirm,
                          message="Enable init.d support (legacy, Android ≤9)?",
                          default=False)

    # ── Recovery ─────────────────────────────────────────────────────────────
    cfg["recovery"] = None
    want_rec = _q(questionary.confirm,
                  message="Search for a custom recovery (TWRP/OrangeFox/SKYHAWK)?",
                  default=False)
    if want_rec:
        rec_type = _q(questionary.select, message="Recovery project:",
                      choices=["twrp", "orangefox", "skyhawk"])
        print(f"  Searching {rec_type} trees for '{cfg['codename']}'...")
        rrepos = device_resolver.search(cfg["codename"], cfg.get("vendor"),
                                         kind="recovery")
        device_resolver.print_repos(rrepos)
        rrep = _pick_repo(rrepos, f"{rec_type} tree")
        if rrep:
            cfg["recovery"] = rrep.clone_url

    # ── Backend ───────────────────────────────────────────────────────────────
    cfg["backend"] = _q(questionary.select, message="Build backend:",
                        choices=["local", "docker", "github-actions"])

    # ── Build options ─────────────────────────────────────────────────────────
    cfg["jobs"]        = int(_q(questionary.text, message="Parallel jobs:", default="4") or "4")
    cfg["lunch_target"]= _q(questionary.text,
                             message="Lunch target (blank = auto):",
                             default="") or None
    cfg["workdir"]     = _q(questionary.text,
                             message="Working directory:",
                             default="./romforge-src")
    cfg["dry_run"]     = _q(questionary.confirm,
                             message="Dry-run first? (prints commands, runs nothing)",
                             default=True)
    cfg["background"]  = False
    if not cfg["dry_run"] and cfg["backend"] == "local":
        cfg["background"] = _q(questionary.confirm,
                                message="Run in background (tmux/nohup)? "
                                        "Survives terminal close / SSH disconnect.",
                                default=True)

    return cfg
