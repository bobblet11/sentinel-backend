import io
import sys
from common.io.utils import indent_with_tab
from contextlib import redirect_stdout

def redirect_and_modify(string_modification_function=indent_with_tab):
    def decorator(func):
        def wrapper(*args, **kwargs):
            string_buffer = io.StringIO()
            with redirect_stdout(string_buffer):
                func(*args, **kwargs)
            captured_output = string_buffer.getvalue()
            if not captured_output:
                return
            lines = captured_output.split("\n")
            if lines[-1] == "":
                modified_lines = [
                    string_modification_function(line) for line in lines[:-1]
                ]
                final_output = "\n".join(modified_lines) + "\n"
            else:
                modified_lines = [string_modification_function(line) for line in lines]
                final_output = "\n".join(modified_lines)

            sys.stdout.write(final_output)

        return wrapper

    return decorator
