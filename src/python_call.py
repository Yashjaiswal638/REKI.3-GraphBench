import os
import sys
from utils import run_in_dir
from subproc import subproc_call

def python_call(pypath, silent = False, timeout = 120):

    def s_print(*args, **kwargs):
        if not silent:
            print(*args, **kwargs)
    dir = os.path.dirname(pypath)
    filename = os.path.basename(pypath)
    cmd = f"{sys.executable} {filename}"
    with run_in_dir(dir):
        run_info = subproc_call(cmd, timeout) # {"out": out_reg, "err": err_reg, "haserror": error_exist}
    if run_info.has_error:
        s_print("python compiling failed")
        return [False, run_info, run_info.err]
    else:
        s_print("python compiling passed")
        return [True, run_info, ""]

def save_py_runinfo(py_run_result, dir):
    """
    save the run info of iverilog to dir
    """
    if not dir.endswith("/"):
        dir += "/"
    run_info_path = dir + "run_info_py.txt"
    lines = ""
    if py_run_result[0]:
        lines += "python compilation passed!\n\n"
    else:
        lines += "python compilation failed!\n\n"
    # output and error of cmd:
    lines += "###output:\n%s\n\n" % (py_run_result[1].out)
    lines += "###error:\n%s\n\n" % (py_run_result[1].err)
    # save to file:
    with open(run_info_path, "w") as f:
        f.write(lines)

def python_call_and_save(pypath, silent = False, timeout = 120):
    """
    run the python file and save the run info
    """
    py_run_result = python_call(pypath, silent, timeout)
    save_py_runinfo(py_run_result, os.path.dirname(pypath))
    return py_run_result
