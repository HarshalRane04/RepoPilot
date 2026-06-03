def local_pr_mode(github_writes_enabled: bool) -> str:
    return "real_github" if github_writes_enabled else "local_record"

