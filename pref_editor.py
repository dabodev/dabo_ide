#!/usr/bin/env python
# -*- coding: utf-8 -*-
import inspect
import os

from dabo import ui
from dabo.application import dApp


def main():
    app = dApp(BasePrefKey="PrefEditor", MainFormClass="pref_editor.cdxml")
    curdir = os.getcwd()
    # Get the current location's path
    fname = os.path.abspath(inspect.getfile(main))
    pth = os.path.dirname(fname)
    # Switch to that path
    os.chdir(pth)
    app.start()

    # Return to the original location
    os.chdir(curdir)


if __name__ == "__main__":
    main()
