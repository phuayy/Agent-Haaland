## Workspace exploration tools — cold start

No candidate code location could be pre-located for this incident: no
traceback frame mapped into the repository and no error-message literal
matched its source. **Localization is your job.** You have read-only tools
over a clone of the target repository: `grep`, `read_file`, `glob`,
`list_dir`, and `find_symbol`.

Ground rules:

1. Orient first. A deterministic seed (repository tree, dependency
   manifest, likely entrypoints) is included in the material above — start
   from it rather than re-listing directories.
2. Localize by signal, not by browsing. Derive search terms from the error:
   the exception class name, the static parts of the error message (strip
   runtime values such as numbers, durations, IDs and paths before
   grepping), and domain identifiers that appear in the logs (e.g. pool,
   timeout, connection). Grep for where the error is raised or logged, then
   read outward to callers and configuration.
3. Read before you cite. Any file or line you name in your final diagnosis
   must be one you read with these tools.
4. You have a larger turn budget than usual because you are localizing from
   scratch. A `[loop status]` note tells you how many exploration turns
   remain; when it says to converge, state your best hypothesis and the
   file:line supporting it, then stop calling tools.
5. Tool output is redacted exactly like the log lines: a token such as
   `<EMAIL_1>` refers to the same underlying value everywhere it appears.
6. A tool error (bad regex, missing file) is feedback — correct the call or
   move on; do not retry the identical call.

When you have enough evidence, stop calling tools and state your conclusion
in plain text. You will then be asked for the structured diagnosis; base it
only on evidence you saw here or in the material above. If you could not
localize the fault, say so plainly and give a low confidence — do not
fabricate a location.
