import glib
import bisect

from BufferUtils import BufferUtils
from Signals import Signals
from Validators import ValidatorMeta
from Validators import ValidatorLatex
import Constants

class Validation(Signals):
	class Bounds(object):
		def __init__(self, start, end):
			self.start = start
			self.end = end
			self.active = False
			self.data = {}
		
		def _get_iter(self, mark):
			if mark.get_deleted():
				return None
			else:
				return mark.get_buffer().get_iter_at_mark(mark)
		
		def _remove_mark(self, mark):
			if not mark.get_deleted():
				mark.get_buffer().delete_mark(mark)
		
		def remove(self):
			self._remove_mark(self.start)
			self._remove_mark(self.end)
			
		def start_iter(self):
			return self._get_iter(self.start)
		
		def end_iter(self):
			return self._get_iter(self.end)
		
		def get_text(self):
			return self.start_iter().get_slice(self.end_iter())
		
		def __cmp__(self, other):
			cm = cmp(self.start, other.start)
			
			if cm == 0:
				return cmp(self.end, other.end)
			else:
				return cm

	class SortedMark(object):
		def __init__(self, line, validator, bounds):
			self.line = line
			self.validator = validator
			self.bounds = bounds
			
			self.bounds.start.set_data(Constants.VALIDATOR_KEY, validator)
			self.bounds.end.set_data(Constants.VALIDATOR_KEY, validator)
			
			self.compare_direct = False
		
		def valid(self):
			return self.validator.match_exact(self.bounds.get_text())
		
		def stop(self):
			self.validator.remove(self.bounds)
			self.bounds.start.set_data(Constants.VALIDATOR_KEY, None)
			self.bounds.end.set_data(Constants.VALIDATOR_KEY, None)
			self.bounds.remove()
		
		def __cmp__(self, other):
			if isinstance(other, Validation.SortedMark):
				if self.compare_direct or other.compare_direct:
					return cmp(super(object, self), other)
				else:
					return cmp(self.line, other.line)
			else:
				return cmp(self.line, other)
		
	def __init__(self, view):
		Signals.__init__(self)

		buf = view.get_buffer()
		self._view = view
		self._buffer = BufferUtils(buf)
		
		self.connect_signal(buf, 'delete-range', self.on_delete_range)
		self.connect_signal_after(buf, 'delete-range', self.on_delete_range_after)
		self.connect_signal(buf, 'cursor-moved', self.on_cursor_moved)
		self.connect_signal(buf, 'save', self.on_save)
		self.connect_signal(buf, 'saved', self.on_saved)
		
		self._buffer.connect_insert_text(self.on_insert_text)
		
		self._invalid_lines = []
		self._invalid_idle_id = 0
		self._sorted_marks = []
		self._active_items = []
		
		self._initialize_validators()
		self._invalidate(*buf.get_bounds())
	
	def _invalidate_all(self):
		active = list(self._sorted_marks)

		for a in active:
			if a in self._active_items:
				self._active_items.remove(a)
				
			self._sorted_marks.remove(a)
			a.stop()
	
	def stop(self):
		if self._invalid_idle_id != 0:
			glib.source_remove(self._invalid_idle_id)
			self._invalid_idle_id = 0
		
		self.disconnect_signals(self._buffer.buffer)
		self._buffer.disconnect_insert_text(self.on_insert_text)

		self._invalidate_all()
	
	def _initialize_validators(self):
		self._validators = [
			ValidatorMeta(self._view),
			ValidatorLatex(self._view)
		]
	
	def iter_with_offset(self, start, offset):
		piter = start.copy()
		piter.forward_chars(offset)

		return piter
		
	def _iters_for_match(self, match, start):
		return [self.iter_with_offset(start, match.start(0)),
				self.iter_with_offset(start, match.end(0))]
	
	def _has_validator_at_iter(self, validator, piter):
		marks = piter.get_marks()
		
		for mark in marks:
			val = mark.get_data(Constants.VALIDATOR_KEY)
			
			if val == validator:
				return True
		
		return False
	
	def _add_validate(self, validator, start, match):
		iters = self._iters_for_match(match, start)
		
		# See if it actually is already active here
		if self._has_validator_at_iter(validator, iters[0]) and \
		   self._has_validator_at_iter(validator, iters[1]):
			return

		bounds = Validation.Bounds(*self._buffer.create_mark_range(iters[0], iters[1]))
		
		item = Validation.SortedMark(iters[0].get_line(), validator, bounds)
		bisect.insort(self._sorted_marks, item)
		
		validator.add(bounds)
		validator.validate(bounds, match)
		
		piter = self._buffer.insert_iter()
		start, end = bounds.start_iter(), bounds.end_iter()
		
		if piter.in_range(start, end):
			self._active_items.append(item)
			validator.enter(bounds)

	def _is_active(self, mark, line):
		return mark.bounds.start_iter().get_line() == line

	def _find_possible_active(self, line):
		if not self._sorted_marks:
			return []
			
		idx = bisect.bisect_left(self._sorted_marks, line)
		length = len(self._sorted_marks)
		ret = []
		
		while idx < length and self._is_active(self._sorted_marks[idx], line):
			ret.append(self._sorted_marks[idx])
			idx += 1
		
		return ret

	def _revalidate_idle(self):
		self._invalid_idle_id = 0
		
		# Try to invalidate any active stuff
		for i in self._invalid_lines:
			active = self._find_possible_active(i)
			
			# See if still matches
			for a in active:
				if not a.valid():
					a.compare_direct = True

					if a in self._active_items:
						self._active_items.remove(a)

					self._sorted_marks.remove(a)
					a.stop()
		
		# And then try to validate some stuff
		for validator in self._validators:
			for i in self._invalid_lines:
				start = self._buffer.get_iter_at_line(i)
				line = self._buffer.line_at_iter(start)
			
				for match in validator.match(line):
					self._add_validate(validator, start, match)
		
		self._invalid_lines = []
		return False
	
	def _invalidate(self, start, end):
		r = [start.get_line(), end.get_line()]
		r.sort()
		
		self._invalid_lines = list(set(self._invalid_lines + range(r[0], r[1] + 1)))

		if self._invalid_idle_id == 0:
			self._invalid_idle_id = glib.idle_add(self._revalidate_idle)

	def on_insert_text(self, start, location):
		self._invalidate(start, location)
		self._insert_text_start = None
		
		diff = location.get_line() - start.get_line()
		
		if diff > 0:
			idx = bisect.bisect_right(self._sorted_marks, start.get_line() + 1)
			
			for i in range(idx, len(self._sorted_marks)):
				self._sorted_marks[i].line += diff
	
	def on_delete_range(self, buf, start, end):
		self._delete_range = [start.get_line(), end.get_line()]
		self._delete_range.sort()
	
	def on_delete_range_after(self, buf, start, end):
		diff = self._delete_range[1] - self._delete_range[0]
		
		if diff > 0:
			self._invalid_lines = filter(lambda x: x <= self._delete_range[0] or x >= self._delete_range[1], self._invalid_lines)

			idx = bisect.bisect_left(self._invalid_lines, self._delete_range[1])
			
			for i in range(idx, len(self._invalid_lines)):
				self._invalid_lines[i] -= diff
			
			idx = bisect.bisect_left(self._sorted_marks, self._delete_range[1])
			
			for i in range(idx, len(self._sorted_marks)):
				self._sorted_marks[i].line -= diff
		
		self._invalidate(start, end)
	
	def cursor_moved_real(self):
		# Update active bounds status
		piter = self._buffer.insert_iter()
		items = self._find_possible_active(piter.get_line())
		
		for item in list(self._active_items):
			start, end = item.bounds.start_iter(), item.bounds.end_iter()

			if not piter.in_range(start, end):
				item.compare_direct = True
				self._active_items.remove(item)
				item.compare_direct = False

				item.validator.exit(item.bounds)
				piter = self._buffer.insert_iter()

		for item in items:
			start, end = item.bounds.start_iter(), item.bounds.end_iter()
			
			if piter.in_range(start, end) and \
			   not (item in self._active_items):	
				self._active_items.append(item)
				item.validator.enter(item.bounds)
				piter = self._buffer.insert_iter()

		return False
	
	def on_cursor_moved(self, doc):
		glib.idle_add(self.cursor_moved_real)
	
	def _store_for_save(self):
		for item in self._sorted_marks:
			item.validator.store_for_save(item.bounds)
	
	def _restore_after_save(self):
		for item in self._sorted_marks:
			item.validator.restore_after_save(item.bounds)
	
	def on_save(self, *args):
		self._store_for_save()
	
	def on_saved(self, *args):
		self._restore_after_save()
