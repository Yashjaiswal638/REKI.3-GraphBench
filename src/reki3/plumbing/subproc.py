import subprocess as sp

class SubprocessResult:
    def __init__(self, out: str, err: str, has_error: bool):
        self.out = out
        self.err = err
        self.has_error = has_error

def subproc_call(cmd: str, timeout=120) -> SubprocessResult:
    timeout_msg = (
        f"program has timed out (time > {timeout}s). "
        "Please check the code. Hints: There might be some infinite loop. "
        "If it is a verilog code, please check if there is a $finish in the code."
    )

    proc = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)

    try:
        out, err = proc.communicate(timeout=timeout)
        return SubprocessResult(
            out=out.decode("utf-8"),
            err=err.decode("utf-8"),
            has_error=proc.returncode != 0
        )
    except sp.TimeoutExpired:
        proc.kill()
        return SubprocessResult(out="", err=timeout_msg, has_error=True)