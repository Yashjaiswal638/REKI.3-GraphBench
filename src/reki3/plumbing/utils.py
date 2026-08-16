import time
import os

class run_in_dir:
    def __init__(self, path):
        self.target = path
    def __enter__(self):
        self.old_dir = os.getcwd()
        if os.path.isabs(self.target):
            os.chdir(self.target)
        else:
            os.chdir(os.path.join(self.old_dir, self.target))

    def __exit__(self, *args):
        os.chdir(self.old_dir)


class Timer:
    def __init__(self, label=None, print_en=True):
        self.label = label
        self.print_en = print_en

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.interval = round(time.time() - self.start, 2)