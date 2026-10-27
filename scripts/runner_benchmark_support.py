"""Memory stop conditions, independent of Docker resource collection."""


def stop_reason(initial_swap, sample, now, low_since):
    if sample["available_bytes"] < 2 * 1024**3:
        low_since = now if low_since is None else low_since
    else:
        low_since = None
    if sample["swap_used_bytes"] - initial_swap > 512 * 1024**2:
        return "swap growth exceeded 512 MiB", low_since
    if low_since is not None and now - low_since >= 5:
        return "available memory below 2 GiB for five seconds", low_since
    return None, low_since


def prepare_pair(directory, prefix, candidate, recovery_directory):
    """Keep completed pairs together; archive partial pairs before rerunning."""
    import json
    import shutil

    summaries = []
    for variant in ("baseline", candidate):
        path = directory / f"{prefix}-{variant}" / "summary.json"
        try:
            summaries.append(json.loads(path.read_text()))
        except (FileNotFoundError, json.JSONDecodeError):
            summaries.append({"complete": False})
    if all(summary.get("complete") for summary in summaries):
        return True
    paths = sorted(path for path in directory.glob(f"{prefix}-*") if path.is_dir())
    if paths:
        recovery_directory.mkdir(parents=True, exist_ok=True)
        for path in paths:
            shutil.move(str(path), str(recovery_directory / path.name))
        (recovery_directory / f"{prefix}-interruption.json").write_text(
            json.dumps(
                {
                    "reason": "Incomplete pair retained after interrupted experiment",
                    "archived_directories": [path.name for path in paths],
                    "rerun_both_variants": True,
                },
                indent=2,
            )
            + "\n"
        )
    return False
