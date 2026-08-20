"""githubkit against a pluggable credential strategy (scm/auth.py):
GitHub App installation tokens in `app` mode (the docs/02 production
choice — least-privilege, short-lived, revocable per repo) or a PAT in
`pat` mode for single-developer setups. Permission set either way:
Contents read/write, Pull requests read/write, Metadata read — nothing
more, per the least-privilege table in docs/09.

**No merge() method exists on this class or on the SCMProvider Protocol.**
That absence, not a runtime check, is the control (docs/09). In `app` mode
it is double-enforced: the App simply is not granted any permission that
could merge or administer the repository."""

from __future__ import annotations

import base64
import contextlib

from githubkit import GitHub
from githubkit.exception import RequestFailed

from haaland.integrations.base import PullRequestResult, RepoRef
from haaland.integrations.scm.auth import GitHubCredentials

_CODEOWNERS_PATHS = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]


def parse_repo_url(repo_url: str) -> RepoRef:
    cleaned = repo_url.strip().removesuffix(".git")
    cleaned = cleaned.removeprefix("https://github.com/").removeprefix("git@github.com:")
    owner, _, repo = cleaned.partition("/")
    if not owner or not repo:
        raise ValueError(f"cannot parse GitHub repo URL: {repo_url!r}")
    return RepoRef(owner=owner, repo=repo)


class GitHubProvider:
    def __init__(self, credentials: GitHubCredentials) -> None:
        self._client = GitHub(credentials.auth_strategy())

    async def get_default_branch_sha(self, ref: RepoRef, branch: str) -> str:
        resp = await self._client.rest.git.async_get_ref(ref.owner, ref.repo, f"heads/{branch}")
        return resp.parsed_data.object_.sha

    async def get_file_contents(self, ref: RepoRef, path: str, sha: str) -> str | None:
        try:
            resp = await self._client.rest.repos.async_get_content(
                ref.owner, ref.repo, path, ref=sha
            )
        except RequestFailed as exc:
            if exc.response.status_code == 404:
                return None
            raise
        data = resp.parsed_data
        if data.encoding != "base64" or data.content is None:
            return None
        return base64.b64decode(data.content).decode("utf-8", errors="replace")

    async def create_branch(self, ref: RepoRef, branch_name: str, base_sha: str) -> None:
        """Create the branch, or reset an existing one back to base_sha.
        Branch names are deterministic per incident+strategy, so a rejected
        draft's second pass (and a job replayed after a crash) reuses the
        same branch — the redraft replaces the old commits rather than
        failing on 422 "Reference already exists"."""
        try:
            await self._client.rest.git.async_create_ref(
                ref.owner, ref.repo, ref=f"refs/heads/{branch_name}", sha=base_sha
            )
        except RequestFailed as exc:
            if exc.response.status_code != 422:
                raise
            await self._client.rest.git.async_update_ref(
                ref.owner, ref.repo, f"heads/{branch_name}", sha=base_sha, force=True
            )

    async def commit_files(
        self, ref: RepoRef, branch_name: str, files: dict[str, str], message: str
    ) -> str:
        last_sha = ""
        for path, content in files.items():
            existing_sha: str | None = None
            try:
                existing = await self._client.rest.repos.async_get_content(
                    ref.owner, ref.repo, path, ref=branch_name
                )
                existing_sha = existing.parsed_data.sha
            except RequestFailed as exc:
                if exc.response.status_code != 404:
                    raise

            resp = await self._client.rest.repos.async_create_or_update_file_contents(
                ref.owner,
                ref.repo,
                path,
                message=message,
                content=base64.b64encode(content.encode("utf-8")).decode("ascii"),
                branch=branch_name,
                sha=existing_sha,
            )
            last_sha = resp.parsed_data.commit.sha
        return last_sha

    async def open_pull_request(
        self,
        ref: RepoRef,
        *,
        branch_name: str,
        base_branch: str,
        title: str,
        body: str,
        labels: list[str],
        reviewers: list[str],
    ) -> PullRequestResult:
        try:
            pr = await self._client.rest.pulls.async_create(
                ref.owner, ref.repo, title=title, body=body, head=branch_name, base=base_branch
            )
            number = pr.parsed_data.number
            url = pr.parsed_data.html_url
        except RequestFailed as exc:
            # 422 "A pull request already exists for this head": the reject-
            # then-redraft loop reuses the incident's branch, so refresh the
            # open PR in place instead of failing the run.
            if exc.response.status_code != 422:
                raise
            existing = await self._client.rest.pulls.async_list(
                ref.owner, ref.repo, head=f"{ref.owner}:{branch_name}", state="open"
            )
            open_prs = existing.parsed_data
            if not open_prs:
                raise
            number = open_prs[0].number
            url = open_prs[0].html_url
            await self._client.rest.pulls.async_update(
                ref.owner, ref.repo, number, title=title, body=body
            )

        if labels:
            await self._client.rest.issues.async_add_labels(ref.owner, ref.repo, number, labels=labels)
        if reviewers:
            # a reviewer not on the repo, or self-review, must not block PR creation
            with contextlib.suppress(RequestFailed):
                await self._client.rest.pulls.async_request_reviewers(
                    ref.owner, ref.repo, number, reviewers=reviewers
                )

        return PullRequestResult(number=number, url=url, branch_name=branch_name)

    async def get_codeowners(self, ref: RepoRef, sha: str) -> str | None:
        for path in _CODEOWNERS_PATHS:
            content = await self.get_file_contents(ref, path, sha)
            if content is not None:
                return content
        return None

    async def clone_url(self, ref: RepoRef) -> str:
        return f"https://github.com/{ref.owner}/{ref.repo}.git"
