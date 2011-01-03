from BufferUtils import BufferUtils
import re
import os
import subprocess
import pango
from gtk import gdk
import tempfile
import signal
import glib
import gtk
import glob

class Validator:
	def __init__(self, view, rule = None):
		self._view = view
		self._buffer = BufferUtils(view.get_buffer())

		if rule:
			self._rule = re.compile(rule)
		else:
			self._rule = None

		self.active = []

	def stop(self):
		for a in self._active:
			a.remove()

		self._buffer = None
		self.active = []

	def add(self, bounds):
		if not bounds in self.active:
			self.active.append(bounds)

	def match_exact(self, text):
		match = self._rule.match(text)

		return match and match.group(0) == text

	def match(self, line):
		# This could be like a cool generator, but it is not
		res = []

		if not self._rule:
			return res

		for m in self._rule.finditer(line):
			res.append(m)

		return res

	def remove(self, bounds):
		self.invalidate(bounds)
		self.active.remove(bounds)

	def iters_for(self, bounds, match, idx):
		start = bounds.start_iter()
		end = start.copy()

		if match.start(0) != 0:
			off = match.start(0)
		else:
			off = 0

		start.forward_chars(match.start(idx) - off)
		end.forward_chars(match.end(idx) - off)

		return start, end

	def validate(self, bounds, matches):
		pass

	def invalidate(self, bounds):
		pass

	def update(self, bounds):
		pass

	def enter(self, bounds):
		pass

	def exit(self, bounds):
		pass

	def store_for_save(self, bounds):
		pass

	def restore_after_save(self, bounds):
		pass

	def mouse_enter(self, bounds):
		pass

	def mouse_exit(self, bounds):
		pass

class ValidatorHide(Validator):
	def __init__(self, view, rule, visible_parts):
		Validator.__init__(self, view, rule)

		self._tag_invisible = self._buffer.create_tag(None, invisible=True, invisible_set=True)
		self._tag_visible = self._buffer.create_tag(None, invisible=False, invisible_set=True)

		self._visible_parts = visible_parts

	def stop(self):
		table = self._buffer.get_tag_table()

		table.remove_tag(self._tag_invisible)
		table.remove_tag(self._tag_visible)

		Validator.stop(self)

	def validate(self, bounds, match):
		self._buffer.apply_tag(self._tag_invisible, *self.iters_for(bounds, match, 0))

		for idx in self._visible_parts:
			self._buffer.apply_tag(self._tag_visible, *self.iters_for(bounds, match, idx))

	def invalidate(self, bounds):
		start, end = bounds.start_iter(), bounds.end_iter()

		self._buffer.remove_tag(self._tag_invisible, start, end)
		self._buffer.remove_tag(self._tag_visible, start, end)

	def enter(self, bounds):
		# Just remove the tags to make it visible
		self.invalidate(bounds)

	def exit(self, bounds):
		# And make it invisible again
		match = self._rule.match(bounds.get_text())

		if not match:
			return

		self.validate(bounds, match)

class ValidatorMeta(ValidatorHide):
	def __init__(self, view):
		ValidatorHide.__init__(self,
							   view,
							   '\{\{\s*([^#]*)\s*:\s*([^:]*[^\s][^:]*?)\s*\}\}',
							   (2,))

class ValidatorEmphasize(ValidatorHide):
	def __init__(self, view):
		ValidatorHide.__init__(self, view, '\'{3}([^\']+)\'{3}', (1,))

class ValidatorStrong(ValidatorHide):
	def __init__(self, view):
		ValidatorHide.__init__(self, view, '_{2}([^_]+)_{2}', (1,))

class ValidatorLatex(ValidatorHide):
	def __init__(self, view):
		ValidatorHide.__init__(self,
		                       view,
		                       '\\$(.*?)\\$',
		                       [])

		self.template = file(os.path.join(os.path.dirname(__file__), 'template.tex')).read()

		self._running_procs = {}
		self._timeout_id = 0

	def get_foreground_color(self):
		style = self._buffer.get_style_scheme().get_style('jft:latex-math')

		if not style:
			style = self._buffer.get_style_scheme().get_style('text')

		if style:
			return style.props.foreground
		else:
			return '#000'

	def _stop_running(self, bounds):
		if bounds in self._running_procs:
			info = self._running_procs[bounds]

			os.kill(info[1].pid, signal.SIGTERM)
			self._cleanup_files(info[0])

			del self._running_procs[bounds]

			if len(self._running_procs) == 0:
				glib.source_remove(self._timeout_id)
				self._timeout_id = 0

	def _remove_pixbuf(self, bounds):
		if 'anchor' in bounds.data:
			if not bounds.data['anchor'].get_deleted():
				mod = self._buffer.get_modified()

				start = self._buffer.get_iter_at_child_anchor(bounds.data['anchor'])
				end = start.copy()
				end.forward_char()

				self._buffer.delete(start, end)

				if not mod:
					self._buffer.set_modified(False)

			del bounds.data['anchor']

	def _show_pixbuf(self, bounds, image = None):
		# Make text invisible
		self._buffer.apply_tag(self._tag_invisible, bounds.start_iter(), bounds.end_iter())

		self._remove_pixbuf(bounds)

		mod = self._buffer.get_modified()
		anchor = self._buffer.create_child_anchor(bounds.start_iter())
		image = gtk.image_new_from_pixbuf(bounds.data['pixbuf'])
		image.show()

		self._view.add_child_at_anchor(image, anchor)
		bounds.data['anchor'] = anchor

		# Also, this will put this thing in the marks, which we don't want, so
		# move the mark
		start = bounds.start_iter()
		start.forward_char()

		self._buffer.move_mark(bounds.start, start)

		if not mod:
			self._buffer.set_modified(False)

	def _cleanup_files(self, name):
		for nm in glob.glob(name + '.*'):
			os.unlink(nm)

	def _process_done(self, bounds, name, ret):
		if ret == 0:
			# there is an image, maybe insert it
			bounds.data['pixbuf'] = gdk.pixbuf_new_from_file(name + '.png')

			# hide the text, all of it
			self._show_pixbuf(bounds)

		self._cleanup_files(name)

	def _check_running_procs(self):
		for bounds in self._running_procs.keys():
			info = self._running_procs[bounds]

			ret = info[1].poll()

			if ret != None:
				self._process_done(bounds, info[0], ret)

				del self._running_procs[bounds]

		if len(self._running_procs) == 0:
			self._timeout_id = 0
			return False
		else:
			return True

	def generate_latex(self, bounds):
		self._stop_running(bounds)

		text = self._rule.match(bounds.get_text()).group(1)

		# Insert colors and font size
		style = self._view.get_style()
		fontsize = (style.font_desc.get_size() / pango.SCALE) * 1.8

		dpi = fontsize * 72.27 / 10

		color = gdk.color_parse(self.get_foreground_color())

		template = self.template.replace('#color', '%f,%f,%f' % (color.red / 65535.0,
		                                                         color.green / 65535.0,
		                                                         color.blue / 65535.0))

		template = template.replace('#expression', text)

		# Write out temporary tex file
		tmp = tempfile.NamedTemporaryFile()
		name = tmp.name
		tmp.close()

		file(name + '.tex', 'w').write(template)

		# Run latex, dvipng etc
		d = os.path.dirname(name)
		b = os.path.basename(name)

		cmd = 'cd "%s" && latex -halt-on-error -interaction=batchmode "%s.tex" && dvipng -o "%s.png" -T tight -D %f -bg Transparent "%s.dvi"' % (d, b, b, dpi, b)

		null = file('/dev/null')

		proc = subprocess.Popen(cmd, shell=True, stdout=null, stderr=null)

		if self._timeout_id == 0:
			self._timeout_id = glib.timeout_add(200, self._check_running_procs)

		self._running_procs[bounds] = [name, proc]

	def validate(self, bounds, match):
		self.generate_latex(bounds)

	def invalidate(self, bounds):
		self._stop_running(bounds)
		self._remove_pixbuf(bounds)

		ValidatorHide.invalidate(self, bounds)

	def enter(self, bounds):
		ValidatorHide.enter(self, bounds)

		self._stop_running(bounds)

		# Hide pixbuf
		self._remove_pixbuf(bounds)

	def store_for_save(self, bounds):
		if 'anchor' in bounds.data:
			self._remove_pixbuf(bounds)
			bounds.data['restore_image'] = True

	def restore_after_save(self, bounds):
		if 'restore_image' in bounds.data:
			self._show_pixbuf(bounds)
			del bounds.data['restore_image']
