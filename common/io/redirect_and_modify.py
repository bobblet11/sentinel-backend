import io
import sys
from contextlib import redirect_stdout
from typing import Callable, List, Tuple

from common.io.utils import indent_with_tab


def redirect_and_modify(
    string_modification_function: Callable = indent_with_tab,
) -> Callable:
    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Tuple, **kwargs: Tuple):
            string_buffer = io.StringIO()

            with redirect_stdout(string_buffer):
                func(*args, **kwargs)

            captured_output: str = string_buffer.getvalue()
            if not captured_output:
                return

            lines: List[str] = captured_output.split("\n")

            if lines[-1] == "":
                modified_lines: List[str] = [
                    string_modification_function(line) for line in lines[:-1]
                ]
                final_output: str = "\n".join(modified_lines) + "\n"
            else:
                modified_lines: List[str] = [
                    string_modification_function(line) for line in lines
                ]
                final_output: str = "\n".join(modified_lines)

            sys.stdout.write(final_output)

        return wrapper

    return decorator
