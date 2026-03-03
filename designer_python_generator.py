# -*- coding: utf-8 -*-
"""
DesignerPythonGenerator: converts a designer dict (as produced by
getDesignerDict()) into a Python class source file.
"""

import ast
import json
import os

# Attributes on the form root that are excluded from the generated output
# (either handled specially or irrelevant at class-definition time).
_FORM_ATTRS_EXCLUDE = frozenset(
    [
        "designerClass",
        "Name",
        "Left",
        "Top",
        "code-ID",
        "classID",
        "SaveRestorePosition",
    ]
)

# Attributes on controls that the generator never emits
_CTRL_ATTRS_EXCLUDE = frozenset(
    [
        "designerClass",
        "sizerInfo",
        "code-ID",
        "classID",
        "rowColPos",
    ]
)

# Attribute names whose values should be treated as integers
_INT_ATTRS = frozenset(
    [
        "Height",
        "Width",
        "Left",
        "Top",
        "FontSize",
        "Spacing",
        "SlotCount",
        "Rows",
        "Columns",
        "HGap",
        "VGap",
        "Order",
        "ColumnCount",
    ]
)

# Sizer class name mapping
_SIZER_CLASS = {
    "LayoutSizer": "dSizer",
    "LayoutBorderSizer": "dBorderSizer",
    "LayoutGridSizer": "dGridSizer",
}

# Orientation shorthands
_ORIENTATION_SHORT = {"Vertical": "v", "Horizontal": "h"}

# Short variable name prefix per dabo class
_CLASS_SHORT_NAME = {
    "dLabel": "label",
    "dButton": "button",
    "dBitmapButton": "bmp_btn",
    "dTextBox": "textbox",
    "dPasswordTextBox": "pwd_textbox",
    "dDateTextBox": "date_textbox",
    "dRichTextBox": "rich_text",
    "dMemo": "memo",
    "dSpinner": "spinner",
    "dSlider": "slider",
    "dCheckBox": "checkbox",
    "dComboBox": "combobox",
    "dDropdownList": "dropdown",
    "dRadioList": "radio_list",
    "dListBox": "list_box",
    "dPanel": "panel",
    "dScrollPanel": "scroll_panel",
    "dBox": "box",
    "dLine": "line",
    "dImage": "image",
    "dBitmap": "bitmap",
    "dHtmlBox": "html",
    "dGrid": "grid",
    "dColumn": "col",
    "dPageFrame": "page_frame",
    "dPageList": "page_list",
    "dPageSelect": "page_select",
    "dPageStyled": "page_styled",
    "dPageFrameNoTabs": "page_frame",
    "dSlidePanelControl": "slide_panel",
    "dSplitter": "splitter",
    "dTreeView": "tree",
    "dToggleButton": "toggle",
    "dTimer": "timer",
    "dMediaControl": "media",
    # Sizers
    "dSizer": "sz",
    "dBorderSizer": "border_sz",
    "dGridSizer": "grid_sz",
}


def _dq(s: str) -> str:
    """Return a double-quoted Python string literal for *s* (Black/Ruff style)."""
    return json.dumps(s)


class DesignerPythonGenerator:
    """Converts a designer dict to Python source."""

    def generate(self, dct: dict, file_stem: str = "") -> str:
        """
        Top-level entry point.  *dct* is what getDesignerDict() returns.
        Returns a string of Python source code.
        """
        self._imports = set()
        self._counters = {}  # short_name → next integer
        self._methods = []  # (method_name, method_source) from child controls
        self._last_var = None  # last control var generated (for grid sizer appends)

        atts = dct.get("attributes", {})
        base_class = dct.get("name", "dForm")
        dc = atts.get("designerClass", "")

        if dc != "DesignerForm":
            raise ValueError(
                f"generate() only supports form-mode dicts "
                f"(designerClass='DesignerForm'), got {dc!r}"
            )

        self._collect_imports(dct)
        class_name = self._make_class_name(base_class, file_stem)
        self._class_name = class_name

        after_init_lines = self._generate_after_init(dct)
        code_dict = dct.get("code", {})
        method_lines = self._generate_methods(code_dict)
        import_block = self._build_import_block(base_class, code_dict)

        lines = ["# -*- coding: utf-8 -*-"]
        lines.append(import_block)
        lines.append("")
        lines.append("")
        lines.append(f"class {class_name}({base_class}):")

        if after_init_lines:
            lines.append("    def afterInit(self):")
            for ln in after_init_lines:
                lines.append("    " + ln if ln.strip() else "")
            lines.append("")

        if method_lines:
            lines.extend(method_lines)

        # Runnable entry point
        lines.append("")
        lines.append("")
        lines.append('if __name__ == "__main__":')
        lines.append("    from dabo.application import dApp")
        lines.append(f"    app = dApp(MainFormClass={class_name})")
        lines.append("    app.start()")
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Import helpers
    # ------------------------------------------------------------------

    def _collect_imports(self, dct: dict):
        """Walk the dict tree and collect all dabo class names needed."""
        atts = dct.get("attributes", {})
        dc = atts.get("designerClass", "")
        name = dct.get("name", "")

        if dc == "DesignerForm":
            self._imports.add(name)
        elif dc == "controlMix":
            self._imports.add(name)
        elif dc in _SIZER_CLASS:
            self._imports.add(_SIZER_CLASS[dc])

        for child in dct.get("children", []):
            self._collect_imports(child)

    def _build_import_block(self, base_class: str, code_dict: dict) -> str:
        """Return the import block as a string."""
        extra_imports = code_dict.get("importStatements", "").strip()

        sorted_imports = sorted(self._imports)
        lines = [f"from dabo.ui import {cls}" for cls in sorted_imports]

        if extra_imports and "events" in extra_imports:
            lines.append("from dabo import events")

        if extra_imports:
            return extra_imports + "\n" + "\n".join(lines)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Class name
    # ------------------------------------------------------------------

    def _make_class_name(self, base_class: str, file_stem: str) -> str:
        """Derive a CamelCase class name from the file stem, or fall back to base class."""
        if file_stem:
            parts = file_stem.replace("-", "_").split("_")
            return "".join(p.title() for p in parts if p)
        return base_class

    # ------------------------------------------------------------------
    # afterInit generation
    # ------------------------------------------------------------------

    def _generate_after_init(self, dct: dict) -> list:
        """Return lines for the afterInit method body (indented 4 spaces)."""
        lines = []
        atts = dct.get("attributes", {})

        # 1. Form-level property assignments
        for key, val in atts.items():
            if key in _FORM_ATTRS_EXCLUDE:
                continue
            py_val = self._python_value(val, key)
            if isinstance(py_val, str):
                lines.append(f"    self.{key} = {_dq(py_val)}")
            else:
                lines.append(f"    self.{key} = {py_val}")

        if lines:
            lines.append("")

        # 2. Sizer / children
        children = dct.get("children", [])
        if children:
            root_child = children[0]
            child_lines = self._generate_object_code(
                root_child,
                parent_var="self",
                sizer_var=None,
                indent=1,
                is_root_sizer=True,
            )
            lines.extend(child_lines)

        return lines

    # ------------------------------------------------------------------
    # Recursive code generation
    # ------------------------------------------------------------------

    def _generate_object_code(
        self,
        dct: dict,
        parent_var: str,
        sizer_var: str | None,
        indent: int,
        is_root_sizer: bool = False,
    ) -> list:
        """Route to the appropriate generator based on designerClass."""
        atts = dct.get("attributes", {})
        dc = atts.get("designerClass", "")
        name = dct.get("name", "")
        pad = "    " * indent

        if dc == "LayoutPanel":
            return []
        elif dc == "LayoutSpacerPanel":
            return self._generate_spacer(dct, sizer_var, pad)
        elif name == "Spacer":
            return self._generate_spacer(dct, sizer_var, pad)
        elif dc == "LayoutSizer":
            return self._generate_layout_sizer(dct, parent_var, sizer_var, indent, is_root_sizer)
        elif dc == "LayoutBorderSizer":
            return self._generate_border_sizer(dct, parent_var, sizer_var, indent, is_root_sizer)
        elif dc == "LayoutGridSizer":
            return self._generate_grid_sizer(dct, parent_var, sizer_var, indent, is_root_sizer)
        elif dc == "controlMix":
            return self._generate_control(dct, parent_var, sizer_var, indent)
        else:
            return []

    def _generate_layout_sizer(self, dct, parent_var, sizer_var, indent, is_root) -> list:
        atts = dct.get("attributes", {})
        orientation = atts.get("Orientation", "Vertical")
        orient_short = _ORIENTATION_SHORT.get(orientation, "v")
        pad = "    " * indent
        lines = []
        sz_var = self._next_var("dSizer")

        if is_root:
            lines.append(f"{pad}{sz_var} = {parent_var}.Sizer = dSizer({_dq(orient_short)})")
        else:
            lines.append(f"{pad}{sz_var} = dSizer({_dq(orient_short)})")

        for child in dct.get("children", []):
            lines.extend(self._generate_object_code(child, parent_var, sz_var, indent))

        if not is_root and sizer_var:
            si_args = self._sizer_info_to_append_args(atts.get("sizerInfo", "{}"))
            lines.append(f"{pad}{sizer_var}.append({sz_var}{si_args})")
            lines.append("")

        return lines

    def _generate_border_sizer(self, dct, parent_var, sizer_var, indent, is_root) -> list:
        atts = dct.get("attributes", {})
        caption = atts.get("Caption", "")
        orientation = atts.get("Orientation", "Vertical")
        orient_short = _ORIENTATION_SHORT.get(orientation, "v")
        pad = "    " * indent
        lines = []
        sz_var = self._next_var("dBorderSizer")

        args = _dq(orient_short)
        if caption:
            args += f", Caption={_dq(caption)}"

        if is_root:
            lines.append(f"{pad}{sz_var} = {parent_var}.Sizer = dBorderSizer({args})")
        else:
            lines.append(f"{pad}{sz_var} = dBorderSizer({args})")

        for child in dct.get("children", []):
            lines.extend(self._generate_object_code(child, parent_var, sz_var, indent))

        if not is_root and sizer_var:
            si_args = self._sizer_info_to_append_args(atts.get("sizerInfo", "{}"))
            lines.append(f"{pad}{sizer_var}.append({sz_var}{si_args})")
            lines.append("")

        return lines

    def _generate_grid_sizer(self, dct, parent_var, sizer_var, indent, is_root) -> list:
        atts = dct.get("attributes", {})
        rows = atts.get("Rows", "0")
        cols = atts.get("Columns", "0")
        hgap = atts.get("HGap", "0")
        vgap = atts.get("VGap", "0")
        pad = "    " * indent
        lines = []
        sz_var = self._next_var("dGridSizer")

        args = f"{rows}, {cols}"
        if hgap != "0" or vgap != "0":
            args += f", HGap={hgap}, VGap={vgap}"

        if is_root:
            lines.append(f"{pad}{sz_var} = {parent_var}.Sizer = dGridSizer({args})")
        else:
            lines.append(f"{pad}{sz_var} = dGridSizer({args})")

        for child in dct.get("children", []):
            child_atts = child.get("attributes", {})
            child_dc = child_atts.get("designerClass", "")
            row_col_str = child_atts.get("rowColPos")

            if child_dc == "LayoutPanel":
                # Empty grid slot — nothing to emit
                continue

            if row_col_str is not None and child_dc == "controlMix":
                # Control placed at a specific grid position
                try:
                    if isinstance(row_col_str, (tuple, list)):
                        r, c = row_col_str
                    else:
                        r, c = eval(row_col_str)
                except Exception:
                    r, c = 0, 0
                self._last_var = None
                ctrl_lines = self._generate_object_code(
                    child, parent_var, sizer_var=None, indent=indent
                )
                # Strip trailing blank so the grid append follows immediately
                while ctrl_lines and not ctrl_lines[-1].strip():
                    ctrl_lines.pop()
                lines.extend(ctrl_lines)
                if self._last_var is not None:
                    si_args = self._sizer_info_to_append_args(child_atts.get("sizerInfo", "{}"))
                    lines.append(
                        f"{pad}{sz_var}.append({self._last_var}{si_args}, row={r}, col={c})"
                    )
                lines.append("")
            else:
                lines.extend(self._generate_object_code(child, parent_var, sz_var, indent))

        if not is_root and sizer_var:
            si_args = self._sizer_info_to_append_args(atts.get("sizerInfo", "{}"))
            lines.append(f"{pad}{sizer_var}.append({sz_var}{si_args})")
            lines.append("")

        return lines

    def _generate_control(
        self,
        dct: dict,
        parent_var: str,
        sizer_var: str | None,
        indent: int,
    ) -> list:
        atts = dict(dct.get("attributes", {}))
        name = dct.get("name", "dPanel")
        code_dict = dct.get("code", {})
        children = dct.get("children", [])
        pad = "    " * indent
        lines = []

        reg_id = atts.get("RegID", "")
        # Guard against invalid identifiers (e.g. RegID accidentally set to "0")
        if reg_id and not reg_id.isidentifier():
            reg_id = ""
        has_code = bool(code_dict)
        has_sizer_child = any(
            c.get("attributes", {}).get("designerClass", "") in _SIZER_CLASS for c in children
        )

        # Determine variable names:
        #   local_var — bare name used as a Python identifier within afterInit
        #   var       — the full assignment target (may have "self." prefix)
        if reg_id:
            local_var = reg_id
            var = f"self.{reg_id}"
        elif has_code:
            local_var = self._next_var(name)
            var = f"self.{local_var}"
        else:
            local_var = self._next_var(name)
            var = local_var

        kwargs = self._attrs_to_kwargs(atts, name)
        kwargs_str = parent_var + (f", {kwargs}" if kwargs else "")

        # Special case: dPanel with a nested sizer child
        if name == "dPanel" and has_sizer_child:
            lines.append(f"{pad}{var} = {name}({kwargs_str})")
            sizer_children_list = [
                c
                for c in children
                if c.get("attributes", {}).get("designerClass", "") in _SIZER_CLASS
            ]
            for sc in sizer_children_list:
                lines.extend(
                    self._generate_object_code(
                        sc, local_var, sizer_var=None, indent=indent, is_root_sizer=True
                    )
                )

        # Special case: dGrid with dColumn children
        elif name == "dGrid" and children and all(c.get("name") == "dColumn" for c in children):
            lines.extend(self._generate_grid_control(dct, parent_var, var, pad))

        # Special case: dPageFrame / dPageFrameNoTabs
        elif name in ("dPageFrame", "dPageFrameNoTabs") and children:
            lines.extend(self._generate_pageframe(dct, parent_var, var, local_var, pad, indent))

        # Special case: dSplitter
        elif name == "dSplitter" and children:
            lines.extend(self._generate_splitter(dct, parent_var, var, pad, indent))

        else:
            lines.append(f"{pad}{var} = {name}({kwargs_str})")

        # Collect methods from child controls into the class-level buffer
        if code_dict:
            for mname, mcode in sorted(code_dict.items()):
                if mname != "importStatements":
                    self._methods.append((mname, mcode.strip()))

        self._last_var = var

        # Append to containing sizer
        if sizer_var:
            si_args = self._sizer_info_to_append_args(atts.get("sizerInfo", "{}"))
            lines.append(f"{pad}{sizer_var}.append({var}{si_args})")

        lines.append("")
        return lines

    def _generate_grid_control(self, dct, parent_var, var, pad) -> list:
        """Generate a dGrid with its dColumn children."""
        atts = dict(dct.get("attributes", {}))
        name = dct.get("name", "dGrid")
        kwargs = self._attrs_to_kwargs(atts, name)
        kwargs_str = parent_var + (f", {kwargs}" if kwargs else "")
        lines = [f"{pad}{var} = {name}({kwargs_str})"]
        cols = sorted(
            dct.get("children", []),
            key=lambda c: int(c.get("attributes", {}).get("Order", 0)),
        )
        for col in cols:
            col_atts = dict(col.get("attributes", {}))
            for drop_key in ("designerClass", "sizerInfo", "Order", "code-ID"):
                col_atts.pop(drop_key, None)
            parts = []
            for k, v in col_atts.items():
                py_val = self._python_value(v, k)
                parts.append(f"{k}={_dq(py_val)}" if isinstance(py_val, str) else f"{k}={py_val}")
            col_kwargs = ", ".join(parts)
            col_args = var + (f", {col_kwargs}" if col_kwargs else "")
            lines.append(f"{pad}{var}.addColumn(dColumn({col_args}))")
        return lines

    def _generate_pageframe(self, dct, parent_var, var, local_var, pad, indent) -> list:
        """Generate a dPageFrame with its pages."""
        atts = dict(dct.get("attributes", {}))
        name = dct.get("name", "dPageFrame")
        children = dct.get("children", [])
        kwargs = self._attrs_to_kwargs(atts, name)
        kwargs_str = parent_var + (f", {kwargs}" if kwargs else "")
        lines = [f"{pad}{var} = {name}({kwargs_str})"]
        lines.append(f"{pad}{var}.PageCount = {len(children)}")
        for i, page in enumerate(children):
            pg_var = f"{local_var}_pg{i}"
            lines.append(f"{pad}{pg_var} = {var}.Pages[{i}]")
            for child in page.get("children", []):
                lines.extend(
                    self._generate_object_code(
                        child, pg_var, sizer_var=None, indent=indent, is_root_sizer=True
                    )
                )
        return lines

    def _generate_splitter(self, dct, parent_var, var, pad, indent) -> list:
        """Generate a dSplitter with its two panels."""
        atts = dict(dct.get("attributes", {}))
        name = dct.get("name", "dSplitter")
        kwargs = self._attrs_to_kwargs(atts, name)
        kwargs_str = parent_var + (f", {kwargs}" if kwargs else "")
        lines = [f"{pad}{var} = {name}({kwargs_str}, createPanes=True)"]
        for i, (panel_attr, child) in enumerate(zip(["Panel1", "Panel2"], dct.get("children", []))):
            pnl_var = f"pnl{i + 1}"
            lines.append(f"{pad}{pnl_var} = {var}.{panel_attr}")
            for pc in child.get("children", []):
                lines.extend(
                    self._generate_object_code(
                        pc, pnl_var, sizer_var=None, indent=indent, is_root_sizer=True
                    )
                )
        return lines

    def _generate_spacer(self, dct: dict, sizer_var: str | None, pad: str) -> list:
        atts = dct.get("attributes", {})
        spacing = atts.get("Spacing", atts.get("size", "10"))
        try:
            spacing = int(spacing)
        except (ValueError, TypeError):
            spacing = 10
        lines = []
        if sizer_var:
            lines.append(f"{pad}{sizer_var}.appendSpacer({spacing})")
        lines.append("")
        return lines

    # ------------------------------------------------------------------
    # Attribute → kwarg helpers
    # ------------------------------------------------------------------

    def _attrs_to_kwargs(self, atts: dict, ctrl_name: str) -> str:
        """Return a comma-separated kwarg string for a constructor call."""
        parts = []
        for key, val in atts.items():
            if key in _CTRL_ATTRS_EXCLUDE or key == "RegID":
                continue
            py_val = self._python_value(val, key)
            parts.append(f"{key}={_dq(py_val)}" if isinstance(py_val, str) else f"{key}={py_val}")
        return ", ".join(parts)

    def _python_value(self, val_str, attr_name: str = ""):
        """Convert a designer attribute string to the best Python literal."""
        if not isinstance(val_str, str):
            return val_str

        if val_str == "True":
            return True
        if val_str == "False":
            return False

        if attr_name in _INT_ATTRS:
            try:
                return int(val_str)
            except ValueError:
                pass

        try:
            return int(val_str)
        except ValueError:
            pass

        try:
            return float(val_str)
        except ValueError:
            pass

        try:
            return ast.literal_eval(val_str)
        except (ValueError, SyntaxError):
            pass

        return val_str

    def _sizer_info_to_append_args(self, si_str) -> str:
        """Convert a sizerInfo string or dict to .append() keyword arguments."""
        if not si_str or si_str == "{}":
            return ""

        if isinstance(si_str, str):
            try:
                si = ast.literal_eval(si_str)
            except (ValueError, SyntaxError):
                return ""
        elif isinstance(si_str, dict):
            si = si_str
        else:
            return ""

        if not si:
            return ""

        parts = []
        border = si.get("Border", 0)
        proportion = si.get("Proportion", 0)
        expand = si.get("Expand", False)
        halign = si.get("HAlign", "Left")
        valign = si.get("VAlign", "Top")
        border_sides = si.get("BorderSides", ["All"])

        if border:
            parts.append(f"border={border}")
        if proportion:
            parts.append(f"proportion={proportion}")
        if expand:
            parts.append("expand=True")
        if halign != "Left":
            parts.append(f"halign={_dq(halign.lower())}")
        if valign != "Top":
            parts.append(f"valign={_dq(valign.lower())}")
        if border_sides != ["All"]:
            parts.append(f"borderSides={json.dumps(border_sides)}")

        if not parts:
            return ""
        return ", " + ", ".join(parts)

    # ------------------------------------------------------------------
    # Method generation
    # ------------------------------------------------------------------

    def _generate_methods(self, code_dict: dict) -> list:
        """Generate class method lines from form code dict + child control methods."""
        all_lines = []

        for mname, mcode in self._methods:
            all_lines.extend(self._format_method(mcode))
            all_lines.append("")

        for mname, mcode in sorted(code_dict.items()):
            if mname == "importStatements":
                continue
            if mname == "afterInit":
                all_lines.append(
                    "    # NOTE: original afterInit renamed to avoid conflict "
                    "with the generated one."
                )
                mcode = mcode.replace("def afterInit(", "def _orig_afterInit(", 1)
            all_lines.extend(self._format_method(mcode))
            all_lines.append("")

        return all_lines

    def _format_method(self, mcode: str) -> list:
        """Indent method source for the class body (4 spaces)."""
        return ["    " + ln for ln in mcode.strip().splitlines()]

    # ------------------------------------------------------------------
    # Variable naming helpers
    # ------------------------------------------------------------------

    def _class_short_name(self, class_name: str) -> str:
        """Return the short variable prefix for a class name."""
        if class_name in _CLASS_SHORT_NAME:
            return _CLASS_SHORT_NAME[class_name]
        # Generic fallback: strip leading "d", lowercase remainder
        if class_name.startswith("d") and len(class_name) > 1:
            return class_name[1].lower() + class_name[2:]
        return class_name.lower()

    def _next_var(self, class_name: str) -> str:
        """Return the next available variable name for *class_name*."""
        short = self._class_short_name(class_name)
        n = self._counters.get(short, 0)
        self._counters[short] = n + 1
        return f"{short}{n}"
