import gedit
import gtksourceview2 as gsv
import gtk
from gtk import gdk
import glib
import re
import time
import os
import gio

from Signals import Signals
from BufferUtils import BufferUtils
from Validation import Validation
from ExportLatex import ExportLatex
from ExportHtml import ExportHtml

import Constants

class DocumentHelper(Signals):
    def __init__(self, view):
        Signals.__init__(self)

        view.set_data(Constants.DOCUMENT_HELPER_KEY, self)

        self._view = view
        self._buffer = None
        self.validation = None

        self.connect_signal(self._view, 'notify::buffer', self.on_notify_buffer)
        self.reset_buffer(self._view.get_buffer())

        self.initialize_event_handlers()

        self._re_any_tag = re.compile('^\s*(\**|[0-9][.0-9]*\))(\s*)((DONE|CHECK|TODO|DEADLINE):\s*(\([0-9]{1,2}((\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)|-[0-9]{1,2}(-[0-9]{2,})?|(January|February|April|May|June|July|August|September|October|November|December))\))?\s* ?)?')
        self._re_list = re.compile('^(\s*)(\*+|[0-9][.0-9]*\))(\s*)')
        self._re_continuations = re.compile('^(\s*)((#+|%+)\s*)')

    def reset_buffer(self, newbuf):
        self._in_mode = False

        if isinstance(newbuf, gsv.Buffer):
            lang = newbuf.get_language()
        else:
            lang = None

        if newbuf == None or lang == None or lang.get_id() != 'jft':
            self.disconnect_signal(self._view, 'key-press-event')

            if self._buffer:
                self._buffer.disconnect_insert_text(self.on_insert_text)

            if self.validation:
                self.validation.stop()
        else:
            self.connect_signal(self._view, 'key-press-event', self.on_key_press_event)
            self.validation = Validation(self._view)
            self.connect_signal(newbuf, 'load', self.on_document_load)
            self.connect_signal(newbuf, 'loaded', self.on_document_loaded)

        if not self._buffer or self._buffer.buffer != newbuf:
            if self._buffer:
                self.disconnect_signals(self._buffer.buffer)

                self.validation = None

            if newbuf:
                self._buffer = BufferUtils(newbuf)
                self.connect_signal(newbuf, 'notify::language', self.on_notify_language)
            else:
                self._buffer = None

        if self._buffer and self._buffer.get_language() and \
           self._buffer.get_language().get_id() == 'jft':
            self._buffer.connect_insert_text(self.on_insert_text)

    def initialize_event_handlers(self):

        self._event_handlers = [
            [('j',), gdk.CONTROL_MASK, self.do_switch_mode, False],
            [('d',), 0, self.do_tag_done, True],
            [('t',), 0, self.do_tag_todo, True],
            [('c',), 0, self.do_tag_check, True],
            [('l',), 0, self.do_tag_deadline, True],
            [('Escape',), 0, self.do_escape_mode, True],
            [('Tab', 'ISO_Left_Tab', 'KP_Tab'), 0, self.do_indent_add, False],
            [('Tab', 'ISO_Left_Tab', 'KP_Tab'), gdk.SHIFT_MASK, self.do_indent_remove, False],
            [('KP_Enter', 'ISO_Enter', 'Return'), 0, self.do_auto_indent, False],
            [('KP_Enter', 'ISO_Enter', 'Return'), gdk.CONTROL_MASK, self.do_auto_indent, False],
            [('p',), 0, self.do_export_pdf, True],
            [('h',), 0, self.do_export_html, True],
        ]

        for handler in self._event_handlers:
            handler[0] = map(lambda x: gtk.gdk.keyval_from_name(x), handler[0])

    def stop(self):
        self.reset_buffer(None)

        self._view.set_data(Constants.DOCUMENT_HELPER_KEY, None)
        self.disconnect_signals(self._view)
        self.disconnect_signals(self._view.get_buffer())

        self._view = None

    def status_message(self, message):
        bar = self._view.get_toplevel().get_statusbar()
        bar.flash_message(0, '%s' % message)

    def enter_mode(self):
        self._in_mode = True
        self.status_message('Entered JFT mode')

    def exit_mode(self):
        self._in_mode = False
        self.status_message('Exited JFT mode')

    def do_switch_mode(self, event):
        if self._in_mode:
            self.exit_mode()
        else:
            self.enter_mode()

    def switch_tag(self, tag):
        line = self._buffer.current_line()
        m = self._re_any_tag.match(line)

        buf = self._buffer
        ins = buf.get_iter_at_mark(buf.get_insert())

        if m and m.group(3):
            # Remove the tag
            start = ins.copy()
            start.set_line_offset(m.end(2))

            end = ins.copy()
            end.set_line_offset(m.end(3))
            buf.delete(start, end)

        ins = None

        if not m:
            ins = buf.get_iter_at_mark(buf.get_insert())
            ins.set_line_offset(0)
        elif m.group(4) != tag:
            ins = buf.get_iter_at_mark(buf.get_insert())
            ins.set_line_offset(m.end(2))

        if ins:
            what = tag + ': '

            if tag == 'DONE':
                what += '(' +  time.strftime('%d %B') + ') '

            buf.insert(ins, what)

        self.exit_mode()
        return True

    def guess_indent(self, indent):
        space = self._view.get_insert_spaces_instead_of_tabs()

        width = self._view.get_indent_width()

        if width == -1:
            width = self._view.get_tab_width()

        if space:
            return ' ' * width, len(indent.replace('\t', '')) / width + indent.count('\t')
        else:
            return '\t', len(indent.replace(' ', '')) + indent.count(' ') / width

    def reindent_ul(self, start, end, indent, match, num):
        self._buffer.delete(start, end)
        self._buffer.insert(start, indent * num + '*' * num)

    def reindent_ol(self, start, end, indent, match, num):
        orig = match.group(2)[0:-1].split('.')

        if len(orig) >= num:
            newt = orig[0:num]
        else:
            newt = list(orig)
            newt.extend(['1' for x in xrange(0, num - len(orig))])

        self._buffer.delete(start, end)
        self._buffer.insert(start, (indent * num) + '.'.join(newt) + ')')

    def reindent_list(self, start, end, indent, match, num):
        if '*' in match.groups(2):
            self.reindent_ul(start, end, indent, match, num)
        else:
            self.reindent_ol(start, end, indent, match, num)

    def list_length(self, item):
        if '*' in item:
            return len(item)
        else:
            return len(item.split('.'))

    def reindent_block(self, start, end):
        """reindent_block(start, end) -> [start, end, [reindents]]

        Reindents a text block using list rules. The block is determined by
        text iters start and end. The new positions of start and end after
        reindenting are returned.
        """

        offsets = range(start.get_line(), end.get_line() + 1)

        # Create marks to keep track of the iters so we can return their new
        # positions
        marks = self._buffer.create_mark_range(start, end, True)
        reindents = []

        self._buffer.begin_user_action()

        for i in offsets:
            line = self._buffer.line_at_offset(i)

            match = self._re_list.match(line)

            if not match:
                continue

            # See if the indentation is correct
            idn, num = self.guess_indent(match.group(1))
            listlen = self.list_length(match.group(2))

            if match.group(1) != idn * num or num != listlen:
                # Incorrect indentation, reindent
                start = self._buffer.get_iter_at_line(i)
                end = start.copy()
                end.forward_chars(match.end(2))

                self.reindent_list(start, end, idn, match, listlen)
                reindents.append(i)

        self._buffer.end_user_action()
        ret = self._buffer.delete_mark_range(marks)
        ret.append(reindents)

        return ret

    def indent_next_level(self, direct):
        bd = self._buffer.get_selection_bounds()

        self._buffer.begin_user_action()

        if not bd or bd[0].equal(bd[1]):
            piter = self._buffer.insert_iter()
            start, end, reindented = self.reindent_block(piter, piter.copy())
            bounds = None
        else:
            start, end, reindented = self.reindent_block(*bd)
            bounds = self._buffer.create_mark_range(start, end, True)

        offsets = range(start.get_line(), end.get_line() + 1)
        ret = False

        if not reindented:
            for i in offsets:
                line = self._buffer.line_at_offset(i)

                match = self._re_list.match(line)

                if not match:
                    continue

                ret = True

                # See if current indent conforms to bullets
                idn, num = self.guess_indent(match.group(1))
                start = self._buffer.get_iter_at_line(i)
                end = start.copy()
                end.forward_chars(match.end(2))

                self.reindent_list(start, end, idn, match, num + direct)
        else:
            ret = True

        if not ret:
            self._buffer.end_user_action()
            return False

        if bounds:
            # Reinstate the selection bounds
            self._buffer.move_mark_to_mark(self._buffer.get_insert(), bounds[0])
            self._buffer.move_mark_to_mark(self._buffer.get_selection_bound(), bounds[1])

            self._buffer.delete_mark_range(bounds)

        self._buffer.end_user_action()
        return True

    def maybe_new_list_item(self, piter):
        # Go back each line
        start = piter.copy()

        while start.backward_line():
            line = self._buffer.line_at_iter(start)

            if line.strip() == '' or (not line.startswith(' ') and not line.startswith('\t')):
                return False

            match = self._re_list.match(line)

            if match:
                self._buffer.begin_user_action()

                nt = self.next_list(match)

                self._buffer.insert(piter, "\n%s%s%s" % (match.group(1), nt, match.group(3)))
                self._buffer.end_user_action()

                self._view.scroll_mark_onscreen(self._buffer.get_insert())
                return True

        return False

    def next_list(self, match):
        if '*' in match.group(2):
            return match.group(2)
        else:
            cur = match.group(2)[0:-1].split('.')
            cur[-1] = str(int(cur[-1]) + 1)

            return '.'.join(cur) + ')'

    def auto_indent(self, event):
        # Insert new line and auto indent
        start = self._buffer.insert_iter()
        begin = start.copy()
        begin.set_line_offset(0)

        line = begin.get_text(start)

        if not event.state & gdk.CONTROL_MASK:
            match = self._re_continuations.match(line)

            if match:
                self._buffer.begin_user_action()
                self._buffer.insert(start, "\n%s%s" % (match.group(1), match.group(2)))
                self._buffer.end_user_action()
                self._view.scroll_mark_onscreen(self._buffer.get_insert())
                return True

        match = self._re_list.match(line)

        if not match:
            if event.state & gdk.CONTROL_MASK:
                return self.maybe_new_list_item(start)

            return False

        # Do special auto indentation, inserting list stuff
        idn, num = self.guess_indent(match.group(1))
        num = self.list_length(match.group(2))

        if event.state & gdk.CONTROL_MASK:
            bullet = ' ' * len(match.group(2))
        else:
            bullet = self.next_list(match)

        self._buffer.begin_user_action()
        self._buffer.insert(start, "\n%s%s%s" % (idn * num, bullet, match.group(3)))
        self._buffer.end_user_action()
        self._view.scroll_mark_onscreen(self._buffer.get_insert())

        return True

    def do_tag_done(self, event):
        return self.switch_tag('DONE')

    def do_tag_check(self, event):
        return self.switch_tag('CHECK')

    def do_tag_todo(self, event):
        return self.switch_tag('TODO')

    def do_tag_deadline(self, event):
        return self.switch_tag('DEADLINE')

    def do_escape_mode(self, event):
        return self.exit_mode()

    def do_indent_add(self, event):
        return self.indent_next_level(1)

    def do_indent_remove(self, event):
        return self.indent_next_level(-1)

    def do_auto_indent(self, event):
        return self.auto_indent(event)

    def do_export(self, exporter):
        doc = self._view.get_buffer()

        ff = doc.get_location()

        if doc.is_local():
            filename = ff.get_path()
            data = file(filename, 'r').read()
        else:
            filename = '/tmp/' + ff.get_basename()
            data = doc.get_text(*doc.get_bounds())

        ex = exporter(data, filename)

        if ex.export():
            ex.show()

        self.exit_mode()
        return True

    def do_export_pdf(self, event):
        return self.do_export(ExportLatex)

    def do_export_html(self, event):
        return self.do_export(ExportHtml)

    def on_key_press_event(self, doc, event):
        defmod = gtk.accelerator_get_default_mod_mask() & event.state

        for handler in self._event_handlers:
            if (not handler[3] or self._in_mode) and event.keyval in handler[0] and (defmod == handler[1]):
                return handler[2](event)

        return False

    def on_notify_language(self, doc, spec):
        self.reset_buffer(doc)

    def on_notify_buffer(self, view, spec):
        self.reset_buffer(view.get_buffer())

    def _meta_line_length(self, line):
        tabsize = self._view.get_tab_width()
        l = len(line) + (tabsize - 1) * line.count("\t")

        r = re.compile('\{\{.*?:\s*(.*?)\s*\}\}')

        for item in r.finditer(line):
            l -= len(item.group(0)) - len(item.group(1))

        r = re.compile('\$.*?\$')
        r2 = re.compile('\\\\[a-z]+')

        for item in r.finditer(line):
            l -= 2

            for i2 in r2.finditer(item.group(0)):
                l -= len(i2.group(0)) - 1

        return l

    def _break_for_wrap(self, line, border):
        tabsize = self._view.get_tab_width()
        unbreakable = []
        ubp = ('$}', '${')
        last = None

        if self._meta_line_length(line) < border:
            return None, None

        for i in range(len(line) - 1, 1, -1):
            first = line[0:i]

            if line[i] in ubp[1] and \
               unbreakable and \
               unbreakable[-1] == ubp[0][ubp[1].index(line[i])]:
                unbreakable.pop()
            elif line[i] in ubp[0]:
                unbreakable.append(line[i])

            if not unbreakable and line[i].isspace():
                if self._meta_line_length(first) < border:
                    second = line[i + 1:]

                    if self._meta_line_length(second) > border - 1:
                        break

                    return first, second
                else:
                    last = i

        if last != None:
            return line[0:last], line[last + 1:]
        else:
            return None, None

    def _wrap_reuse_next(self, offset):
        start = self._buffer.get_iter_at_line(offset + 1)

        if start.get_line() == offset:
            return False

        end = start.copy()
        end.forward_to_line_end()

        line = start.get_text(end)

        return not (self._re_list.match(line) or line.strip() == "" or line.strip().startswith('%') or line.strip().startswith('#'))

    def on_insert_text(self, start, end):
        self._buffer.block_insert_text(self.on_insert_text)

        sl = start.get_line()
        el = end.get_line()

        # First reindent block if there is more than 1 line of text
        if sl != el:
            start, end, reindented = self.reindent_block(start, end)

        tabsize = self._view.get_tab_width()
        border = self._view.get_right_margin_position()

        while sl <= el:
            # See if the line needs any wrapping
            line = self._buffer.line_at_offset(sl)

            tabs = line.count("\t")

            # Do the wrapping magic
            orig, wrapped = self._break_for_wrap(line, border)

            if wrapped:
                start = self._buffer.get_iter_at_line(sl)
                start.forward_chars(len(orig))
                end = start.copy()
                end.forward_to_line_end()

                ins = self._buffer.get_iter_at_mark(self._buffer.get_insert())
                movecursor = ins.in_range(start, end) or ins.equal(end)
                moveinit = end.get_line_offset() - ins.get_line_offset()

                self._buffer.delete(start, end)

                if self._wrap_reuse_next(sl):
                    # Prepend wrapped text to next line

                    start = self._buffer.get_iter_at_line(sl + 1)
                    self._buffer.iter_skip_space(start)
                    self._buffer.insert(start, wrapped)

                    if not wrapped[-1].isspace():
                        self._buffer.insert(start, " ")
                        start.backward_char()

                    start.backward_chars(moveinit)

                    if movecursor:
                        self._buffer.move_mark(self._buffer.get_insert(), start)
                        self._buffer.move_mark(self._buffer.get_selection_bound(), start)

                    if el == sl:
                        el += 1
                else:
                    # Create a new line, but calculate the indentation
                    match = self._re_list.match(line)

                    if match:
                        idn, num = self.guess_indent(match.group(1))
                        num = self.list_length(match.group(2))

                        indent = "%s%s%s" % (idn * num, ' ' * len(match.group(2)), match.group(3))
                    else:
                        start = self._buffer.get_iter_at_line(sl)
                        begin = start.copy()
                        self._buffer.iter_skip_space(start)

                        indent = begin.get_text(start)

                    self._buffer.insert(end, "\n%s%s" % (indent, wrapped))

                    end.backward_chars(moveinit)

                    if movecursor:
                        self._buffer.move_mark(self._buffer.get_insert(), end)
                        self._buffer.move_mark(self._buffer.get_selection_bound(), end)

                    el += 1

            sl += 1

        self._buffer.unblock_insert_text(self.on_insert_text)

    def on_document_load(self, doc, uri, encoding, linepos, create):
        self._buffer.block_insert_text(self.on_insert_text)

    def on_document_loaded(self, doc, arg1):
        self._buffer.unblock_insert_text(self.on_insert_text)

# vi:ex:ts=4:et
