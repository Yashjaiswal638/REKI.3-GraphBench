import os
from utils import run_in_dir
from subproc import subproc_call

IVERILOG_PATH = "iverilog"
IVERILOG_VVP_PATH = "vvp"

def iverilog_call(dir, silent = False, timeout = 120):

    def s_print(*args, **kwargs):
        if not silent:
            print(*args, **kwargs)

    if not dir.endswith("/"):
        dir += "/"
    v_files = [f for f in os.listdir(dir) if f.endswith(".v")]
    vlist_str = " ".join(v_files)
    # vvp_filename = "%s.vvp"%(task_id)
    vvp_filename = "run.vvp"
    # cmd1 = "iverilog -g2012 -o %s %s"%(vvp_filename, vlist_str) # used to be vvp_path
    cmd1 = "%s -g2012 -o %s %s"%(IVERILOG_PATH, vvp_filename, vlist_str) # used to be vvp_path
    s_print(cmd1)
    with run_in_dir(dir):
        run1_info = subproc_call(cmd1, timeout) # {"out": out_reg, "err": err_reg, "haserror": error_exist}
    if run1_info.has_error:
        s_print("iverilog compiling failed")
        return [False, cmd1, run1_info, None, None, run1_info.err]
    cmd2 = "%s %s"%(IVERILOG_VVP_PATH, vvp_filename) # used to be vvp_path
    s_print(cmd2)
    with run_in_dir(dir):
        run2_info = subproc_call(cmd2, timeout)
    if run2_info.has_error:
        s_print("vvp failed")
        return [False, cmd1, run1_info, cmd2, run2_info, run2_info.err]
    return [True, cmd1, run1_info, cmd2, run2_info, '']

def save_iv_runinfo(ivrun_info, dir):

    run_info_path = dir + "run_info.txt"
    lines = ""
    if ivrun_info[0]:
        lines += "iverilog simulation passed!\n\n"
    else:
        lines += "iverilog simulation failed!\n\n"
    # cmd 1:
    if ivrun_info[1] is not None:
        lines += "iverilog cmd 1:\n%s\n" % (ivrun_info[1])
    # output and error of cmd 1:
    if ivrun_info[2] is not None:
        lines += "iverilog cmd 1 output:\n%s\n" % (ivrun_info[2].out)
        lines += "iverilog cmd 1 error:\n%s\n" % (ivrun_info[2].err)
    # cmd 2:
    if ivrun_info[3] is not None:
        lines += "iverilog cmd 2:\n%s\n" % (ivrun_info[3])
    # output and error of cmd 2:
    if ivrun_info[4] is not None:
        lines += "iverilog cmd 2 output:\n%s\n" % (ivrun_info[4].out)
        lines += "iverilog cmd 2 error:\n%s\n" % (ivrun_info[4].err)
    # save to file:
    with open(run_info_path, "w") as f:
        f.write(lines)

def iverilog_call_and_save(dir, silent = False, timeout = 120):
    """
    run the iverilog and save the run info
    """
    iv_run_result = iverilog_call(dir, silent, timeout)
    save_iv_runinfo(iv_run_result, dir)
    return iv_run_result
