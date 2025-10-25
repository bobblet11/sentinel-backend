import json
import os
import datetime
from common.io.redirect_and_modify import redirect_and_modify, indent_with_space

@redirect_and_modify(string_modification_function=indent_with_space)
def exec():
        pass

if __name__ == "__main__":
        
        print(f"\n\nmain.py is being run. It is currently {datetime.datetime.now()}")
        
        exec()

        print(f"\n\nmain.py is finished. It is currently {datetime.datetime.now()}")
