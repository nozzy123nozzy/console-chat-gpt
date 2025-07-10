# This module is originally [simple-term-menu](https://github.com/IngoMeyer441/simple-term-menu)
# This module rewrite simple-term-menu with urwid package, to work under windows native.
import urwid
import argparse
import io
import os
import re
import shlex
import signal
import subprocess
import sys
import typing
from locale import getlocale
from types import FrameType
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Match,
    Optional,
    Pattern,
    Sequence,
    Set,
    TextIO,
    Tuple,
    Union,
    cast,
)
from collections.abc import Hashable
from typing_extensions import Literal

__author__ = "Takahide Nojima"
__email__ = "nozzy123nozzy@gmail.com"
__copyright__ = "Copyright © 2025 Takahide Nojima All rights reserved."
__license__ = "MIT"
__version_info__ = (1, 0, 0)
__version__ = ".".join(map(str, __version_info__))


DEFAULT_ACCEPT_KEYS = ("enter",)
DEFAULT_CLEAR_MENU_ON_EXIT = True
DEFAULT_CLEAR_SCREEN = False
DEFAULT_CYCLE_CURSOR = True
DEFAULT_EXIT_ON_SHORTCUT = True
DEFAULT_MENU_CURSOR = "> "
DEFAULT_MENU_CURSOR_STYLE = ("light red", "bold")
DEFAULT_MENU_HIGHLIGHT_STYLE = ("standout",)
DEFAULT_MULTI_SELECT = False
DEFAULT_MULTI_SELECT_CURSOR = "[*] "
DEFAULT_MULTI_SELECT_CURSOR_BRACKETS_STYLE = ("light gray",)
DEFAULT_MULTI_SELECT_CURSOR_STYLE = ("yellow", "bold")
DEFAULT_MULTI_SELECT_KEYS = (" ", "tab")
DEFAULT_MULTI_SELECT_SELECT_ON_ACCEPT = True
DEFAULT_PREVIEW_BORDER = True
DEFAULT_PREVIEW_SIZE = 0.25
DEFAULT_PREVIEW_TITLE = "preview"
DEFAULT_QUIT_KEYS = ("escape", "q", "ctrl-g")
DEFAULT_SEARCH_CASE_SENSITIVE = False
DEFAULT_SEARCH_HIGHLIGHT_STYLE = ("black", "yellow", "bold")
DEFAULT_SEARCH_KEY = "/"
DEFAULT_SHORTCUT_BRACKETS_HIGHLIGHT_STYLE = ("light gray",)
DEFAULT_SHORTCUT_KEY_HIGHLIGHT_STYLE = ("light blue",)
DEFAULT_SHOW_MULTI_SELECT_HINT = False
DEFAULT_SHOW_SEARCH_HINT = False
DEFAULT_SHOW_SHORTCUT_HINTS = False
DEFAULT_SHOW_SHORTCUT_HINTS_IN_STATUS_BAR = True
DEFAULT_STATUS_BAR_BELOW_PREVIEW = False
DEFAULT_STATUS_BAR_STYLE = ("yellow", "black")
MIN_VISIBLE_MENU_ENTRIES_COUNT = 3

class InvalidParameterCombinationError(Exception):
    pass


class InvalidStyleError(Exception):
    pass


class NoMenuEntriesError(Exception):
    pass


class PreviewCommandFailedError(Exception):
    pass


class UnknownMenuEntryError(Exception):
    pass

def get_locale() -> str:
    user_locale = getlocale()[1]
    if user_locale is None:
        return "ascii"
    else:
        return user_locale.lower()

def convert_to_AttrSpec(style_specs: tuple):
    non_color_styles=('bold','italics','underline',
                      'blink','standout','strikethrough')
    if len(style_specs) == 0:
        return urwid.AttrSpec('default','default',16)
    fg_lst=[]
    bg_lst=[]
    for idx,val in enumerate(style_specs):
        if idx == 0:
            fg_lst.append(val)
        elif val in non_color_styles:
            fg_lst.append(val)
        else:
            bg_lst.append(val)
    if len(bg_lst)==0:
        bg_lst=['default']
    return urwid.AttrSpec(",".join(fg_lst),",".join(bg_lst),16)

class TerminalMenu:
    class CheckBoxItemEx(urwid.CheckBox):
        """A custom widget for the multiple select menu """

        def __init__( self,
                    label: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]],
                    state: bool | Literal["mixed"] ,
                    multi_select_cursor: str ,
                    multi_select_cursor_brackets_style: tuple[Hashable, str] | list[str | tuple[Hashable, str]],
                    multi_select_cursor_style: tuple[Hashable, str] | list[str | tuple[Hashable, str]],
                    multi_select_keys: tuple[str] | list[str],
                    accept_keys:tuple[str] | list[str]
                    ):
            super().__init__(label,state)

            self.preview_argument = None
            trimed_multi_select_cursor = multi_select_cursor.strip()
            self.states[True] = urwid.SelectableIcon([(multi_select_cursor_brackets_style,
                                                       trimed_multi_select_cursor[0]),
                                                (multi_select_cursor_style,trimed_multi_select_cursor[1]),
                                                (multi_select_cursor_brackets_style,trimed_multi_select_cursor[2])], 1)
            default_attrs = convert_to_AttrSpec(('default','default'))
            self.states[False] = urwid.SelectableIcon([(default_attrs,trimed_multi_select_cursor[0]+" "+\
                    trimed_multi_select_cursor[2])],1)
            for keystr in multi_select_keys:
                self._command_map[keystr] = urwid.ACTIVATE                                              
            self._accept_keys = accept_keys

        def keypress(self, size: tuple[int] | tuple[()], key: str) -> str | None:
            if key in self._accept_keys:
                self.state = True
                raise urwid.ExitMainLoop()

            if self._command_map[key] != urwid.ACTIVATE:
                return key

            self.toggle_state()
            return None

        def set_preview_argument(self,argument: str) -> None:
            self.preview_argument=argument

        def get_preview_argument(self) -> str:
            return self.preview_argument

    class MenuItem(urwid.Text):
        """A custom widget for the simple select menu """

        def __init__(self, label: str | tuple[Hashable, str] | list[str | tuple[Hashable, str]],
                    cursor: str,cursor_style: tuple[Hashable,str],menu_highlight_style: tuple[Hashable,str],
                    accept_keys:tuple[str] | list[str]
                     ) -> None:
            self.cursor = cursor
            self.cursor_style = cursor_style
            super().__init__([(convert_to_AttrSpec(('default','default')), " "*(len(self.cursor))+label)],
                             wrap='any')
            self.state = False
            self.preview_argument = None
            self._original_label=label
            self.menu_highlight_style = menu_highlight_style
            self._accept_keys = accept_keys
            self._selectable = True

        def keypress(self, size: tuple[int] | tuple[()], key: str) -> str | None:
            if key in self._accept_keys:
                self.state = True
                raise urwid.ExitMainLoop()
            return key

        def mouse_event(
            self,
            size: tuple[int] | tuple[()],
            event: str,
            button: int,
            col: int,
            row: int,
            focus: bool,
        ) -> bool | None:
            if event == "mouse release":
                self.state = True
                raise urwid.ExitMainLoop()
            return False

        def get_state(self) -> bool:
            return self.state

        def get_label(self) -> str:
            """Just alias to text."""
            return self._original_label

        def set_preview_argument(self,argument: str) -> None:
            self.preview_argument=argument

        def get_preview_argument(self) -> str:
            return self.preview_argument

        def render(
            self,
            size: tuple[int] | tuple[()],  # type: ignore[override]
            focus: bool = False,
        ) -> urwid.TextCanvas:
            if focus:
                self.set_text([(self.cursor_style,self.cursor),(self.menu_highlight_style,self._original_label)])
            else:
                self.set_text([(convert_to_AttrSpec(('default','default'))," "*len(self.cursor)+self._original_label)])
            return super().render(size,focus)

    class CustomKeyboardListBox(urwid.ListBox):
        signals: typing.ClassVar[list[str]] = ["searchmodified"]

        def __init__(self, body: urwid.ListWalker | Iterable[urwid.Widget],cycle_cursor: bool,
                    search_case_sensitive: bool,
                    search_highlight_style: Iterable[str],
                    search_key: str ) -> None:
            super().__init__(body)
            self._cycle_cursor = cycle_cursor
            self._filtering_mode = False
            self._filtering_strings = ""
            self._original_body = body
            self._search_key = search_key
            self._search_case_sensitive = search_case_sensitive
            self._search_highlight_style = search_highlight_style

        def filterd_ListWalker(self):
            if self._search_case_sensitive:
                candidate_widgets = [ a_widget for a_widget in self._original_body \
                    if self._filtering_strings.casefold() in a_widget.original_widget.get_label().casefold() ]
            else:
                candidate_widgets = [ a_widget for a_widget in self._original_body \
                    if self._filtering_strings in a_widget.original_widget.get_label() ]
            if len(candidate_widgets) == 0:
                return None
            return candidate_widgets

        def keypress(self, size, key: str):
            if self._cycle_cursor == True:
                if key == 'down':
                    try:
                        # Move focus to the next item
                        self.focus_position += 1
                    except IndexError:
                        # If at the end, wrap around to the start
                        self.focus_position = 0
                    return None  # Key handled

                if key == 'up':
                    if self.focus_position == 0:
                        # If at the start, wrap around to the end
                        self.focus_position = len(self.body) - 1
                    else:
                        # Move focus to the previous item
                        self.focus_position -= 1
                    return None  # Key handled
            
            if self._filtering_mode == False:
                if key == self._search_key:
                    self._filtering_mode = True
                    self._emit("searchmodified","/")
                    return None
            else:
                if len(key)==1 and 34 < ord(key) and ord(key)<=124:
                    self._filtering_strings = self._filtering_strings + key
                elif key=="backspace" or key=="delete":
                    l = len(self._filtering_strings)
                    if l == 1: 
                        self._filtering_strings = ""
                        self._filtering_mode = False
                        self.body = self._original_body
                        self._emit("searchmodified","")
                        return None
                    self._filtering_strings = self._filtering_strings[:l-1]
                else:
                    # For other keys, use the default behavior
                    return super().keypress(size, key)

                filterd_listwalker = self.filterd_ListWalker()
                if filterd_listwalker is not None:
                    self.body = urwid.SimpleListWalker(filterd_listwalker)
                self._emit("searchmodified","/"+self._filtering_strings)
                return None
        
    def __init__(
        self,
        menu_entries: Iterable[str],
        *,
        accept_keys: Iterable[str] = DEFAULT_ACCEPT_KEYS,
        clear_menu_on_exit: bool = DEFAULT_CLEAR_MENU_ON_EXIT,
        clear_screen: bool = DEFAULT_CLEAR_SCREEN,
        cursor_index: Optional[int] = None,
        cycle_cursor: bool = DEFAULT_CYCLE_CURSOR,
        exit_on_shortcut: bool = DEFAULT_EXIT_ON_SHORTCUT,
        menu_cursor: Optional[str] = DEFAULT_MENU_CURSOR,
        menu_cursor_style: Optional[Iterable[str]] = DEFAULT_MENU_CURSOR_STYLE,
        menu_highlight_style: Optional[Iterable[str]] = DEFAULT_MENU_HIGHLIGHT_STYLE,
        multi_select: bool = DEFAULT_MULTI_SELECT,
        multi_select_cursor: str = DEFAULT_MULTI_SELECT_CURSOR,
        multi_select_cursor_brackets_style: Optional[Iterable[str]] = DEFAULT_MULTI_SELECT_CURSOR_BRACKETS_STYLE,
        multi_select_cursor_style: Optional[Iterable[str]] = DEFAULT_MULTI_SELECT_CURSOR_STYLE,
        multi_select_empty_ok: bool = False,
        multi_select_keys: Optional[Iterable[str]] = DEFAULT_MULTI_SELECT_KEYS,
        multi_select_select_on_accept: bool = DEFAULT_MULTI_SELECT_SELECT_ON_ACCEPT,
        preselected_entries: Optional[Iterable[Union[str, int]]] = None,
        preview_border: bool = DEFAULT_PREVIEW_BORDER,
        preview_command: Optional[Union[str, Callable[[str], str]]] = None,
        preview_size: float = DEFAULT_PREVIEW_SIZE,
        preview_title: str = DEFAULT_PREVIEW_TITLE,
        quit_keys: Iterable[str] = DEFAULT_QUIT_KEYS,
        raise_error_on_interrupt: bool = False,
        search_case_sensitive: bool = DEFAULT_SEARCH_CASE_SENSITIVE,
        search_highlight_style: Optional[Iterable[str]] = DEFAULT_SEARCH_HIGHLIGHT_STYLE,
        search_key: Optional[str] = DEFAULT_SEARCH_KEY,
        shortcut_brackets_highlight_style: Optional[Iterable[str]] = DEFAULT_SHORTCUT_BRACKETS_HIGHLIGHT_STYLE,
        shortcut_key_highlight_style: Optional[Iterable[str]] = DEFAULT_SHORTCUT_KEY_HIGHLIGHT_STYLE,
        show_multi_select_hint: bool = DEFAULT_SHOW_MULTI_SELECT_HINT,
        show_multi_select_hint_text: Optional[str] = None,
        show_search_hint: bool = DEFAULT_SHOW_SEARCH_HINT,
        show_search_hint_text: Optional[str] = None,
        show_shortcut_hints: bool = DEFAULT_SHOW_SHORTCUT_HINTS,
        show_shortcut_hints_in_status_bar: bool = DEFAULT_SHOW_SHORTCUT_HINTS_IN_STATUS_BAR,
        skip_empty_entries: bool = False,
        status_bar: Optional[Union[str, Iterable[str], Callable[[str], str]]] = None,
        status_bar_below_preview: bool = DEFAULT_STATUS_BAR_BELOW_PREVIEW,
        status_bar_style: Optional[Iterable[str]] = DEFAULT_STATUS_BAR_STYLE,
        title: Optional[Union[str, Iterable[str]]] = None
    ):
        (
            self._menu_entries,
            self._shortcut_keys,
            self._preview_arguments,
            self._skip_indices,
        ) = self._extract_shortcuts_menu_entries_and_preview_arguments(menu_entries)
        self._shortcuts_defined = any(key is not None for key in self._shortcut_keys)
        self._accept_keys = tuple(accept_keys)
        self._clear_menu_on_exit = clear_menu_on_exit
        self._clear_screen = clear_screen
        self._cycle_cursor = cycle_cursor
        self._cursor_index = cursor_index
        self._multi_select_empty_ok = multi_select_empty_ok
        self._exit_on_shortcut = exit_on_shortcut
        self._menu_cursor = menu_cursor if menu_cursor is not None else ""
        self._menu_cursor_style = convert_to_AttrSpec(tuple(menu_cursor_style) if menu_cursor_style is not None else ())
        self._menu_highlight_style = convert_to_AttrSpec(tuple(menu_highlight_style) if menu_highlight_style is not None else ())
        self._multi_select = multi_select
        self._multi_select_cursor = multi_select_cursor
        self._multi_select_cursor_brackets_style = convert_to_AttrSpec(
            tuple(multi_select_cursor_brackets_style) if multi_select_cursor_brackets_style is not None else ()
        )
        self._multi_select_cursor_style = convert_to_AttrSpec(
            tuple(multi_select_cursor_style) if multi_select_cursor_style is not None else ()
        )
        self._multi_select_keys = tuple(multi_select_keys) if multi_select_keys is not None else ()
        self._multi_select_select_on_accept = multi_select_select_on_accept
        if preselected_entries and not self._multi_select:
            raise InvalidParameterCombinationError(
                "Multi-select mode must be enabled when preselected entries are given."
            )
        self._preselected_entries = preselected_entries
        self._preview_border = preview_border
        self._preview_command = preview_command
        self._preview_size = preview_size
        self._preview_title = preview_title
        self._quit_keys = tuple(quit_keys)
        self._raise_error_on_interrupt = raise_error_on_interrupt
        self._search_case_sensitive = search_case_sensitive
        self._search_highlight_style = convert_to_AttrSpec(tuple(search_highlight_style) if search_highlight_style is not None else ())
        self._search_key = search_key
        self._shortcut_brackets_highlight_style = convert_to_AttrSpec(
            tuple(shortcut_brackets_highlight_style) if shortcut_brackets_highlight_style is not None else ()
        )
        self._shortcut_key_highlight_style = convert_to_AttrSpec(
            tuple(shortcut_key_highlight_style) if shortcut_key_highlight_style is not None else ()
        )
        self._show_search_hint = show_search_hint
        self._show_search_hint_text = show_search_hint_text
        self._show_shortcut_hints = show_shortcut_hints
        self._show_shortcut_hints_in_status_bar = show_shortcut_hints_in_status_bar
        self._status_bar_func = None  # type: Optional[Callable[[str], str]]
        self._status_bar_lines = None  # type: Optional[Tuple[str, ...]]
        if callable(status_bar):
            self._status_bar_func = status_bar
        else:
            self._status_bar_lines = self._setup_title_or_status_bar_lines(
                status_bar,
                show_shortcut_hints and show_shortcut_hints_in_status_bar,
                self._menu_entries,
                self._shortcut_keys,
                False,
            )
        self._status_bar_below_preview = status_bar_below_preview
        self._status_bar_style = convert_to_AttrSpec(tuple(status_bar_style) if status_bar_style is not None else ())
        self._title_lines = self._setup_title_or_status_bar_lines(
            title,
            show_shortcut_hints and not show_shortcut_hints_in_status_bar,
            self._menu_entries,
            self._shortcut_keys,
            True,
        )
        self._show_multi_select_hint = show_multi_select_hint
        self._show_multi_select_hint_text = show_multi_select_hint_text
        self._chosen_accept_key = None  # type: Optional[str]
        self._chosen_menu_index = None  # type: Optional[int]
        self._chosen_menu_indices = None  # type: Optional[Tuple[int, ...]]
        self._paint_before_next_read = False
        self._previous_displayed_menu_height = None  # type: Optional[int]
        self._reading_next_key = False
        self._user_locale = get_locale()

    def _extract_shortcuts_menu_entries_and_preview_arguments(
        self,
        entries: Iterable[str],
    ) -> Tuple[List[str], List[Optional[str]], List[Optional[str]], List[int]]:
        separator_pattern = re.compile(r"([^\\])\|")
        escaped_separator_pattern = re.compile(r"\\\|")
        menu_entry_pattern = re.compile(r"^(?:\[(\S)\]\s*)?([^\x1F]+)(?:\x1F([^\x1F]*))?")
        shortcut_keys = []  # type: List[Optional[str]]
        menu_entries = []  # type: List[str]
        preview_arguments = []  # type: List[Optional[str]]
        skip_indices = []  # type: List[int]
    
        for idx, entry in enumerate(entries):
            if entry is None or (entry == "" and skip_empty_entries):
                shortcut_keys.append(None)
                menu_entries.append("")
                preview_arguments.append(None)
                skip_indices.append(idx)
            else:
                unit_separated_entry = escaped_separator_pattern.sub("|", separator_pattern.sub("\\1\x1F", entry))
                match_obj = menu_entry_pattern.match(unit_separated_entry)
                # this is none in case the entry was an emtpy string which
                # will be interpreted as a separator
                assert match_obj is not None
                shortcut_key = match_obj.group(1)
                display_text = match_obj.group(2)
                preview_argument = match_obj.group(3)
                shortcut_keys.append(shortcut_key)
                menu_entries.append(display_text)
                preview_arguments.append(preview_argument)
    
        return menu_entries, shortcut_keys, preview_arguments, skip_indices
    
    def _get_shortcut_hints_line(
        self,
        menu_entries: Iterable[str],
        shortcut_keys: Iterable[Optional[str]],
        shortcut_hints_in_parentheses: bool,
    ) -> Optional[str]:
        shortcut_hints_line = []
        default_attrs = convert_to_AttrSpec(('default','default'))
        for shortcut_key, menu_entry in zip(shortcut_keys, menu_entries):
            if shortcut_key is not None:
                shortcut_hints_line.append((self._shortcut_brackets_highlight_style,"["))
                shortcut_hints_line.append((self._shortcut_key_highlight_style,shortcut_key))
                shortcut_hints_line.append((self._shortcut_brackets_highlight_style,"]"))
                shortcut_hints_line.append((default_attrs,menu_entry+", "))

        if len(shortcut_hints_line) != 0:
            if shortcut_hints_in_parentheses:
                return [(default_attrs,"(")] + shortcut_hints_line + [(default_attrs,")")]
            else:
                return shortcut_hints_line
        return None
        
    def _setup_title_or_status_bar_lines(
        self,
        title_or_status_bar: Optional[Union[str, Iterable[str]]],
        show_shortcut_hints: bool,
        menu_entries: Iterable[str],
        shortcut_keys: Iterable[Optional[str]],
        shortcut_hints_in_parentheses: bool,
    ) -> str:
        if title_or_status_bar is None:
            lines = []  # type: List[str]
        elif isinstance(title_or_status_bar, str):
            lines = [title_or_status_bar]
        else:
            lines = list(title_or_status_bar)
        if show_shortcut_hints:
            shortcut_hints_line = self._get_shortcut_hints_line(
                menu_entries, shortcut_keys, shortcut_hints_in_parentheses
            )
            if shortcut_hints_line is not None:
                lines = lines + shortcut_hints_line
        return lines

    def show(self) -> Optional[Union[int, Tuple[int, ...]]]:
        self._title_widget = urwid.Text(self._title_lines) if self._title_lines != "" else None

        self._menu_item_widget_list = []
        item_list_for_menu_walker = []
        entry_to_index = {}
        for idx,a_menu_item in enumerate(self._menu_entries):
            if self._multi_select == True:
                menu_item_widget = self.CheckBoxItemEx(a_menu_item,False,self._multi_select_cursor,
                                                       self._multi_select_cursor_brackets_style,
                                                       self._multi_select_cursor_style,
                                                       self._multi_select_keys,
                                                       self._accept_keys)
                entry_to_index[a_menu_item]=idx
            else:
                menu_item_widget =  self.MenuItem(a_menu_item,self._menu_cursor,self._menu_cursor_style,
                                                  self._menu_highlight_style,
                                                  self._accept_keys)
            if self._preview_arguments[idx] is not None:
                menu_item_widget.set_preview_argument(self._preview_argument[idx])
            self._menu_item_widget_list.append(menu_item_widget)
            item_list_for_menu_walker.append(urwid.AttrMap(menu_item_widget,"selectable","focus"))

        if self._multi_select == True and self._preselected_entries is not None:
            for item in self._preselected_entries:
                if isinstance(item, int):
                    if 0 <= item < len(self._menu_item_widget_list):
                        self._menu_item_widget_list[item].set_state(True)
                    else:
                        raise IndexError(
                            f"Error: {item} is outside the allowable range of 0..{len(self._menu_item_widget_list)-1}."
                        )
                elif isinstance(item, str):
                    try:
                        self._menu_item_widget_list[item].set_state(True)
                    except KeyError as e:
                        raise UnknownMenuEntryError(f'Pre-selection "{item}" is not a valid menu entry.') from e
                else:
                    raise ValueError('"preselected_entries" must either contain integers or strings.')

        self._menu_walker = urwid.SimpleListWalker(item_list_for_menu_walker)
        self._menu_widget = self.CustomKeyboardListBox(self._menu_walker,self._cycle_cursor,
                                                  self._search_case_sensitive,self._search_highlight_style,
                                                  self._search_key)
        if self._cursor_index is not None:
            self._menu_widget.set_focus(self._cursor_index)
        self._search_text_widget = urwid.Text("")
        self._status_bar_widget = urwid.Text(self._status_bar_lines) if self._status_bar_lines != "" else None

        self._preview_widget = None
        self._preview_listbox_widget = None
        if self._preview_command is not None:
            def get_preview_string(forcused_original_widget) -> Optional[str]:
                assert self._preview_command is not None
                preview_argument = forcused_original_widget.get_preview_argument()
                if preview_argument is None:
                    preview_argument = forcused_original_widget.get_label()
                if isinstance(self._preview_command, str):
                    try:
                        preview_process = subprocess.Popen(
                            [cmd_part.format(preview_argument) for cmd_part in shlex.split(self._preview_command)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        assert preview_process.stdout is not None
                        preview_string = (
                            io.TextIOWrapper(preview_process.stdout, encoding=self._user_locale, errors="replace")
                            .read()
                            .strip()
                        )
                    except subprocess.CalledProcessError as e:
                        raise PreviewCommandFailedError(
                            e.stderr.decode(encoding=self._user_locale, errors="replace").strip()
                        ) from e
                else:
                    preview_string = self._preview_command(preview_argument) if preview_argument is not None else ""
                return preview_string

            def create_new_walker(contents:str):
                if contents is None or len(contents)==0:
                    return urwid.SimpleListWalker([urwid.Text(" ")])
                screen_hight = (urwid.raw_display.Screen().get_cols_rows())[1]
                load_max = int(screen_hight*self._preview_size)+1
                lines = [ urwid.Text(a_line, wrap = 'any') for a_line in (contents.split("\n"))[:load_max] ]
                return urwid.SimpleListWalker(lines) 

            def list_change_cb() -> None:
                self._preview_listbox_widget.body = create_new_walker(
                    get_preview_string(self._menu_widget.focus.original_widget))

            self._preview_listbox_widget = urwid.ListBox(create_new_walker(
                    get_preview_string(self._menu_widget.focus.original_widget)))
            self._preview_listbox_widget._selectable = False # block the focus driffted
            if self._preview_border == True:
                self._preview_widget = urwid.LineBox(self._preview_listbox_widget,
                                                     title=self._preview_title,title_align='left') \
                    if self._preview_title is not None else urwid.LineBox(self._preview_listbox_widget)
            else:
                self._preview_widget = self._preview_listbox_widget
            urwid.connect_signal(self._menu_walker, 'modified', list_change_cb)

        def search_text_change_cb(widget,newtext) -> None:
            self._search_text_widget.set_text(newtext)

        urwid.connect_signal(self._menu_widget,'searchmodified',search_text_change_cb)
        piled_render_directives = []
        if self._title_widget is not None:
            piled_render_directives.append(('pack',self._title_widget))
        if self._preview_command is not None:
            piled_render_directives.append(('weight',(1.0-self._preview_size),self._menu_widget))
        else:
            piled_render_directives.append(('weight',1,self._menu_widget))
        piled_render_directives.append(('pack',self._search_text_widget))
        if self._status_bar_below_preview == False and self._status_bar_widget is not None:
            piled_render_directives.append(('pack',self._status_bar_widget))
        if self._preview_command is not None:
            piled_render_directives.append(('weight',self._preview_size,self._preview_widget))
        if self._status_bar_below_preview == True and self._status_bar_widget is not None:
            piled_render_directives.append(('pack',self._status_bar_widget))
            
        self._screen_widget =  urwid.Pile(piled_render_directives)
        def show_or_exit(key: str) -> None:
            if key in self._quit_keys:
                raise urwid.ExitMainLoop()
        
        loop = urwid.MainLoop(self._screen_widget, unhandled_input=show_or_exit)
        loop.run()
        choices = [ idx for idx,widget in enumerate(self._menu_item_widget_list) \
                if widget.get_state() == True ]
        return choices if 0 < len(choices) else None


def get_argumentparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
%(prog)s creates simple interactive menus in the terminal and returns the selected entry as exit code.
""",
    )
    parser.add_argument(
        "-s", "--case-sensitive", action="store_true", dest="case_sensitive", help="searches are case sensitive"
    )
    parser.add_argument(
        "-X",
        "--no-clear-menu-on-exit",
        action="store_false",
        dest="clear_menu_on_exit",
        help="do not clear the menu on exit",
    )
    parser.add_argument(
        "-l",
        "--clear-screen",
        action="store_true",
        dest="clear_screen",
        help="clear the screen before the menu is shown",
    )
    parser.add_argument(
        "--cursor",
        action="store",
        dest="cursor",
        default=DEFAULT_MENU_CURSOR,
        help='menu cursor (default: "%(default)s")',
    )
    parser.add_argument(
        "-i",
        "--cursor-index",
        action="store",
        dest="cursor_index",
        type=int,
        default=0,
        help="initially selected item index",
    )
    parser.add_argument(
        "--cursor-style",
        action="store",
        dest="cursor_style",
        default=",".join(DEFAULT_MENU_CURSOR_STYLE),
        help='style for the menu cursor as comma separated list (default: "%(default)s")',
    )
    parser.add_argument("-C", "--no-cycle", action="store_false", dest="cycle", help="do not cycle the menu selection")
    parser.add_argument(
        "-E",
        "--no-exit-on-shortcut",
        action="store_false",
        dest="exit_on_shortcut",
        help="do not exit on shortcut keys",
    )
    parser.add_argument(
        "--highlight-style",
        action="store",
        dest="highlight_style",
        default=",".join(DEFAULT_MENU_HIGHLIGHT_STYLE),
        help='style for the selected menu entry as comma separated list (default: "%(default)s")',
    )
    parser.add_argument(
        "-m",
        "--multi-select",
        action="store_true",
        dest="multi_select",
        help="Allow the selection of multiple entries (implies `--stdout`)",
    )
    parser.add_argument(
        "--multi-select-cursor",
        action="store",
        dest="multi_select_cursor",
        default=DEFAULT_MULTI_SELECT_CURSOR,
        help='multi-select menu cursor (default: "%(default)s")',
    )
    parser.add_argument(
        "--multi-select-cursor-brackets-style",
        action="store",
        dest="multi_select_cursor_brackets_style",
        default=",".join(DEFAULT_MULTI_SELECT_CURSOR_BRACKETS_STYLE),
        help='style for brackets of the multi-select menu cursor as comma separated list (default: "%(default)s")',
    )
    parser.add_argument(
        "--multi-select-cursor-style",
        action="store",
        dest="multi_select_cursor_style",
        default=",".join(DEFAULT_MULTI_SELECT_CURSOR_STYLE),
        help='style for the multi-select menu cursor as comma separated list (default: "%(default)s")',
    )
    parser.add_argument(
        "--multi-select-keys",
        action="store",
        dest="multi_select_keys",
        default=",".join(DEFAULT_MULTI_SELECT_KEYS),
        help=('key for toggling a selected item in a multi-selection (default: "%(default)s", '),
    )
    parser.add_argument(
        "--multi-select-no-select-on-accept",
        action="store_false",
        dest="multi_select_select_on_accept",
        help=(
            "do not select the currently highlighted menu item when the accept key is pressed "
            "(it is still selected if no other item was selected before)"
        ),
    )
    parser.add_argument(
        "--multi-select-empty-ok",
        action="store_true",
        dest="multi_select_empty_ok",
        help=("when used together with --multi-select-no-select-on-accept allows returning no selection at all"),
    )
    parser.add_argument(
        "-p",
        "--preview",
        action="store",
        dest="preview_command",
        help=(
            "Command to generate a preview for the selected menu entry. "
            '"{}" can be used as placeholder for the menu text. '
            'If the menu entry has a data component (separated by "|"), this is used instead.'
        ),
    )
    parser.add_argument(
        "--no-preview-border",
        action="store_false",
        dest="preview_border",
        help="do not draw a border around the preview window",
    )
    parser.add_argument(
        "--preview-size",
        action="store",
        dest="preview_size",
        type=float,
        default=DEFAULT_PREVIEW_SIZE,
        help='maximum height of the preview window in fractions of the terminal height (default: "%(default)s")',
    )
    parser.add_argument(
        "--preview-title",
        action="store",
        dest="preview_title",
        default=DEFAULT_PREVIEW_TITLE,
        help='title of the preview window (default: "%(default)s")',
    )
    parser.add_argument(
        "--search-highlight-style",
        action="store",
        dest="search_highlight_style",
        default=",".join(DEFAULT_SEARCH_HIGHLIGHT_STYLE),
        help='style of matched search patterns (default: "%(default)s")',
    )
    parser.add_argument(
        "--search-key",
        action="store",
        dest="search_key",
        default=DEFAULT_SEARCH_KEY,
        help=(
            'key to start a search (default: "%(default)s", '
            '"none" is treated a special value which activates the search on any letter key)'
        ),
    )
    parser.add_argument(
        "--shortcut-brackets-highlight-style",
        action="store",
        dest="shortcut_brackets_highlight_style",
        default=",".join(DEFAULT_SHORTCUT_BRACKETS_HIGHLIGHT_STYLE),
        help='style of brackets enclosing shortcut keys (default: "%(default)s")',
    )
    parser.add_argument(
        "--shortcut-key-highlight-style",
        action="store",
        dest="shortcut_key_highlight_style",
        default=",".join(DEFAULT_SHORTCUT_KEY_HIGHLIGHT_STYLE),
        help='style of shortcut keys (default: "%(default)s")',
    )
    parser.add_argument(
        "--show-multi-select-hint",
        action="store_true",
        dest="show_multi_select_hint",
        help="show a multi-select hint in the status bar",
    )
    parser.add_argument(
        "--show-multi-select-hint-text",
        action="store",
        dest="show_multi_select_hint_text",
        help=(
            "Custom text which will be shown as multi-select hint. Use the placeholders {multi_select_keys} and "
            "{accept_keys} if appropriately."
        ),
    )
    parser.add_argument(
        "--show-search-hint",
        action="store_true",
        dest="show_search_hint",
        help="show a search hint in the search line",
    )
    parser.add_argument(
        "--show-search-hint-text",
        action="store",
        dest="show_search_hint_text",
        help=(
            "Custom text which will be shown as search hint. Use the placeholders {key} for the search key "
            "if appropriately."
        ),
    )
    parser.add_argument(
        "--show-shortcut-hints",
        action="store_true",
        dest="show_shortcut_hints",
        help="show shortcut hints in the status bar",
    )
    parser.add_argument(
        "--show-shortcut-hints-in-title",
        action="store_false",
        dest="show_shortcut_hints_in_status_bar",
        default=True,
        help="show shortcut hints in the menu title",
    )
    parser.add_argument(
        "--skip-empty-entries",
        action="store_true",
        dest="skip_empty_entries",
        help="Interpret an empty string in menu entries as an empty menu entry",
    )
    parser.add_argument(
        "-b",
        "--status-bar",
        action="store",
        dest="status_bar",
        help="status bar text",
    )
    parser.add_argument(
        "-d",
        "--status-bar-below-preview",
        action="store_true",
        dest="status_bar_below_preview",
        help="show the status bar below the preview window if any",
    )
    parser.add_argument(
        "--status-bar-style",
        action="store",
        dest="status_bar_style",
        default=",".join(DEFAULT_STATUS_BAR_STYLE),
        help='style of the status bar lines (default: "%(default)s")',
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        dest="stdout",
        help=(
            "Print the selected menu index or indices to stdout (in addition to the exit status). "
            'Multiple indices are separated by ";".'
        ),
    )
    parser.add_argument("-t", "--title", action="store", dest="title", help="menu title")
    parser.add_argument(
        "-V", "--version", action="store_true", dest="print_version", help="print the version number and exit"
    )
    parser.add_argument("entries", action="store", nargs="*", help="the menu entries to show")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-r",
        "--preselected_entries",
        action="store",
        dest="preselected_entries",
        help="Comma separated list of strings matching menu items to start pre-selected in a multi-select menu.",
    )
    group.add_argument(
        "-R",
        "--preselected_indices",
        action="store",
        dest="preselected_indices",
        help="Comma separated list of numeric indexes of menu items to start pre-selected in a multi-select menu.",
    )
    return parser

class AttributeDict(dict):  # type: ignore
    def __getattr__(self, attr: str) -> Any:
        return self[attr]

    def __setattr__(self, attr: str, value: Any) -> None:
        self[attr] = value

def parse_arguments() -> AttributeDict:
    parser = get_argumentparser()
    args = AttributeDict({key: value for key, value in vars(parser.parse_args()).items()})
    if not args.print_version and not args.entries:
        raise NoMenuEntriesError("No menu entries given!")
    if args.skip_empty_entries:
        args.entries = [entry if entry != "None" else None for entry in args.entries]
    if args.cursor_style != "":
        args.cursor_style = tuple(args.cursor_style.split(","))
    else:
        args.cursor_style = None
    if args.highlight_style != "":
        args.highlight_style = tuple(args.highlight_style.split(","))
    else:
        args.highlight_style = None
    if args.search_highlight_style != "":
        args.search_highlight_style = tuple(args.search_highlight_style.split(","))
    else:
        args.search_highlight_style = None
    if args.shortcut_key_highlight_style != "":
        args.shortcut_key_highlight_style = tuple(args.shortcut_key_highlight_style.split(","))
    else:
        args.shortcut_key_highlight_style = None
    if args.shortcut_brackets_highlight_style != "":
        args.shortcut_brackets_highlight_style = tuple(args.shortcut_brackets_highlight_style.split(","))
    else:
        args.shortcut_brackets_highlight_style = None
    if args.status_bar_style != "":
        args.status_bar_style = tuple(args.status_bar_style.split(","))
    else:
        args.status_bar_style = None
    if args.multi_select_cursor_brackets_style != "":
        args.multi_select_cursor_brackets_style = tuple(args.multi_select_cursor_brackets_style.split(","))
    else:
        args.multi_select_cursor_brackets_style = None
    if args.multi_select_cursor_style != "":
        args.multi_select_cursor_style = tuple(args.multi_select_cursor_style.split(","))
    else:
        args.multi_select_cursor_style = None
    if args.multi_select_keys != "":
        args.multi_select_keys = tuple(args.multi_select_keys.split(","))
    else:
        args.multi_select_keys = None
    if args.search_key.lower() == "none":
        args.search_key = None
    if args.show_shortcut_hints_in_status_bar:
        args.show_shortcut_hints = True
    if args.multi_select:
        args.stdout = True
    if args.preselected_entries is not None:
        args.preselected = list(args.preselected_entries.split(","))
    elif args.preselected_indices is not None:
        args.preselected = list(map(int, args.preselected_indices.split(",")))
    else:
        args.preselected = None
    return args


def main() -> None:
    try:
        args = parse_arguments()
    except SystemExit:
        sys.exit(0)  # Error code 0 is the error case in this program
    except NoMenuEntriesError as e:
        print(str(e), file=sys.stderr)
        sys.exit(0)
    if args.print_version:
        print("{}, version {}".format(os.path.basename(sys.argv[0]), __version__))
        sys.exit(0)
    try:
        terminal_menu = TerminalMenu(
            menu_entries=args.entries,
            clear_menu_on_exit=args.clear_menu_on_exit,
            clear_screen=args.clear_screen,
            cursor_index=args.cursor_index,
            cycle_cursor=args.cycle,
            exit_on_shortcut=args.exit_on_shortcut,
            menu_cursor=args.cursor,
            menu_cursor_style=args.cursor_style,
            menu_highlight_style=args.highlight_style,
            multi_select=args.multi_select,
            multi_select_cursor=args.multi_select_cursor,
            multi_select_cursor_brackets_style=args.multi_select_cursor_brackets_style,
            multi_select_cursor_style=args.multi_select_cursor_style,
            multi_select_empty_ok=args.multi_select_empty_ok,
            multi_select_keys=args.multi_select_keys,
            multi_select_select_on_accept=args.multi_select_select_on_accept,
            preselected_entries=args.preselected,
            preview_border=args.preview_border,
            preview_command=args.preview_command,
            preview_size=args.preview_size,
            preview_title=args.preview_title,
            search_case_sensitive=args.case_sensitive,
            search_highlight_style=args.search_highlight_style,
            search_key=args.search_key,
            shortcut_brackets_highlight_style=args.shortcut_brackets_highlight_style,
            shortcut_key_highlight_style=args.shortcut_key_highlight_style,
            show_multi_select_hint=args.show_multi_select_hint,
            show_multi_select_hint_text=args.show_multi_select_hint_text,
            show_search_hint=args.show_search_hint,
            show_search_hint_text=args.show_search_hint_text,
            show_shortcut_hints=args.show_shortcut_hints,
            show_shortcut_hints_in_status_bar=args.show_shortcut_hints_in_status_bar,
            skip_empty_entries=args.skip_empty_entries,
            status_bar=args.status_bar,
            status_bar_below_preview=args.status_bar_below_preview,
            status_bar_style=args.status_bar_style,
            title=args.title,
        )
    except (InvalidParameterCombinationError, InvalidStyleError, UnknownMenuEntryError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(0)
    chosen_entries = terminal_menu.show()
    if chosen_entries is None:
        sys.exit(0)
    else:
        if isinstance(chosen_entries, Iterable):
            if args.stdout:
                print(",".join(str(entry + 1) for entry in chosen_entries))
            sys.exit(chosen_entries[0] + 1)
        else:
            chosen_entry = chosen_entries
            if args.stdout:
                print(chosen_entry + 1)
            sys.exit(chosen_entry + 1)


if __name__ == "__main__":
    main()

