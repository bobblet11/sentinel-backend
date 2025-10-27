import io
import sys
from contextlib import redirect_stdout


def indent_with_tab(s):
        return f"\t{s}" 
def indent_with_space(s):
        return f"        {s}" 

def prRed(s): return "\033[91m {}\033[00m".format(s)
def prGreen(s): return "\033[92m {}\033[00m".format(s)
def prYellow(s): return "\033[93m {}\033[00m".format(s)
def prLightPurple(s): return"\033[94m {}\033[00m".format(s)
def prPurple(s): return "\033[95m {}\033[00m".format(s)
def prCyan(s): return "\033[96m {}\033[00m".format(s)
def prLightGray(s): return "\033[97m {}\033[00m".format(s)

def redirect_and_modify(string_modification_function = indent_with_tab):
        def decorator(func):
                def wrapper(*args, **kwargs):
                        string_buffer = io.StringIO()
                        with redirect_stdout(string_buffer):
                                func(*args, **kwargs)
                        captured_output = string_buffer.getvalue()
                        if not captured_output:
                                return
                        lines = captured_output.split('\n')
                        if lines[-1] == '':
                                modified_lines = [string_modification_function(line) for line in lines[:-1]]
                                final_output = "\n".join(modified_lines) + "\n"
                        else:
                                modified_lines = [string_modification_function(line) for line in lines]
                                final_output = "\n".join(modified_lines)
                                        
                        sys.stdout.write(final_output)
                return wrapper
        return decorator
