import re

class BufferUtils:
	def __init__(self, buf):
		self.buffer = buf	
	
	def line_at_iter(self, start):
		start = start.copy()

		start.set_line_offset(0)
		end = start.copy()
		
		if not end.ends_line():
			end.forward_to_line_end()
	
		return start.get_slice(end)

	def line_at_offset(self, offset):
		return self.line_at_iter(self.buffer.get_iter_at_line(offset))
	
	def insert_iter(self):
		return self.buffer.get_iter_at_mark(self.buffer.get_insert())

	def current_line(self):
		return self.line_at_iter(self.insert_iter())
	
	def move_mark_to_mark(self, mark, target):
		self.buffer.move_mark(mark, self.buffer.get_iter_at_mark(target))

	def create_mark_range(self, start, end):
		return (self.create_mark(None, start, True),
				self.create_mark(None, end, False))

	def __getattr__(self, name):
		return getattr(self.buffer, name)
