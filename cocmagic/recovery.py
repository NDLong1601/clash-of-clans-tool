"""Unwind an input transaction before any further action can use its frame."""


class RecoveryInterrupted(RuntimeError):
    pass


class RuntimeWriteError(OSError):
    pass


def remote_job_cleanup(pidfile):
    """Wait for a uniquely named remote script to exit before releasing input.

    A host adb timeout alone does not terminate its remote shell. TERM traps
    execute after its current foreground command; kill -0 confirms that command
    cannot be followed by another stale input before the caller resumes.
    pidfile is generated internally from a UUID, never supplied by a user.
    """
    return (
        f"cleanup_rc=0; if [ -f {pidfile} ]; then job_pid=$(cat {pidfile}); "
        'kill "$job_pid" 2>/dev/null; n=0; '
        'while kill -0 "$job_pid" 2>/dev/null && [ "$n" -lt 14 ]; do '
        "sleep 0.1; n=$((n+1)); done; "
        'if kill -0 "$job_pid" 2>/dev/null; then cleanup_rc=1; fi; fi; '
        f'if [ "$cleanup_rc" -eq 0 ]; then rm -f {pidfile}; fi'
    )
