import gedit
import gtksourceview2 as gsv
import gtk
from gtk import gdk
import glib
import re
import time

from Signals import Signals
from BufferUtils import BufferUtils
from Validation import Validation
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
		
		self._re_any_tag = re.compile('^\s*(\**)(\s*)((DONE|CHECK|TODO|DEADLINE):\s*(\([0-9]{1,2}((\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)|-[0-9]{1,2}(-[0-9]{2,})?|(January|February|April|May|June|July|August|September|October|November|December))\))?\s* ?)?')
		self._re_list = re.compile('^(\s*)(\*+)')

	def reset_buffer(self, newbuf):
		self._in_mode = False
		
		if isinstance(newbuf, gsv.Buffer):
			lang = newbuf.get_language()
		else:
			lang = None

		if newbuf == None or lang == None or lang.get_id() != 'jft':
			self.disconnect_signal(self._view, 'key-press-event')
			
			if self.validation:
				self.validation.stop()
		else:
			self.connect_signal(self._view, 'key-press-event', self.on_key_press_event)
			self.validation = Validation(self._view)
		
		if not self._buffer or self._buffer.buffer != newbuf:
			if self._buffer:
				self.disconnect_signals(self._buffer.buffer)
				self.validation = None
			
			if newbuf:
				self._buffer = BufferUtils(newbuf)
				self.connect_signal(newbuf, 'notify::language', self.on_notify_language)
			else:
				self._buffer = None

	def initialize_event_handlers(self):
		self._event_handlers = [
			[('j',), gdk.CONTROL_MASK, self.do_switch_mode, False],
			[('d',), gdk.CONTROL_MASK, self.do_tag_done, True],
			[('t',), gdk.CONTROL_MASK, self.do_tag_todo, True],
			[('c',), gdk.CONTROL_MASK, self.do_tag_check, True],
			[('l',), gdk.CONTROL_MASK, self.do_tag_deadline, True],
			[('Escape',), 0, self.do_escape_mode, True],
			[('Tab', 'ISO_Left_Tab', 'KP_Tab'), 0, self.do_indent_add, False],
			[('Tab', 'ISO_Left_Tab', 'KP_Tab'), gdk.SHIFT_MASK, self.do_indent_remove, False],
			[('KP_Enter', 'ISO_Enter', 'Return'), 0, self.do_auto_indent, False],
			[('KP_Enter', 'ISO_Enter', 'Return'), gdk.CONTROL_MASK, self.do_auto_indent, False]
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
	
	def reindent_list(self, start, end, indent, num):
		self._buffer.delete(start, end)
		self._buffer.insert(start, indent * num + '*' * num)
	
	def do_indent(self, direct):
		# See if the current line is a list
		bd = self._buffer.get_selection_bounds()
		
		if len(bd) == 0:
			start = end = self._buffer.insert_iter()
		else:
			start, end = bd

		offsets = range(start.get_line(), end.get_line() + 1)
		
		if not start.equal(end):
			bounds = (self._buffer.create_mark(None, start, True),
					  self._buffer.create_mark(None, end, False))
		else:
			bounds = None
		
		ret = False
		reindent = False
		indent_info = []
		
		for i in offsets:
			line = self._buffer.line_at_offset(i)

			m = self._re_list.match(line)
		
			if not m:
				continue
			
			ret = True
		
			# See if current indent conforms to bullets
			idn, num = self.guess_indent(m.group(1))
			
			indent_info.append((idn, num, m))
			
			if m.group(1) != idn * num or num != len(m.group(2)):
				reindent = True

		if not ret:
			return False
		
		self._buffer.begin_user_action()
		
		for i in range(0, len(offsets)):
			start = self._buffer.get_iter_at_line(offsets[i])
			info = indent_info[i]
			idn, num, match = info

			end = start.copy()
			end.forward_chars(match.end(2))

			if reindent:
				self.reindent_list(start, end, idn, len(match.group(2)))
			else:
				self.reindent_list(start, end, idn, num + direct)
		
		if bounds:
			self._buffer.move_mark_to_mark(self._buffer.get_insert(), bounds[0])
			self._buffer.move_mark_to_mark(self._buffer.get_selection_bound(), bounds[1])
			self._buffer.delete_mark(bounds[0])
			self._buffer.delete_mark(bounds[1])
		
		self._buffer.end_user_action()
		return True

	def maybe_new_list_item(self, piter):
		# Go back each line
		start = piter.copy()
		
		while start.backward_line():
			line = self._buffer.line_at_iter(start)
			match = self._re_list.match(line)
			
			if match:
				self._buffer.begin_user_action()
				self._buffer.insert(piter, "\n%s " % (match.group(0),))
				self._buffer.end_user_action()
				
				self._view.scroll_mark_onscreen(self._buffer.get_insert())
				return True
		
		return False
	
	def auto_indent(self, event):
		# Insert new line and auto indent
		start = self._buffer.insert_iter()
		line = self._buffer.line_at_iter(start)
		
		match = self._re_list.match(line)
		
		if not match:
			if event.state & gdk.CONTROL_MASK:
				return self.maybe_new_list_item(start)

			return False
		
		# Do special auto indentation, inserting list stuff
		idn, num = self.guess_indent(match.group(1))

		self._buffer.begin_user_action()
		
		if match.group(1) != idn * num or num != len(match.group(2)):
			# First reindent this one then
			end = start.copy()
			end.forward_chars(match.end(2))

			num = len(match.group(2))
			self.reindent_list(start, end, idn, num)
		
		if event.state & gdk.CONTROL_MASK:
			bullet = ' '
		else:
			bullet = '*'

		self._buffer.insert(start, "\n%s%s " % (idn * num, bullet * num))
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
		return self.do_indent(1)
	
	def do_indent_remove(self, event):
		return self.do_indent(-1)
	
	def do_auto_indent(self, event):
		return self.auto_indent(event)
	
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
