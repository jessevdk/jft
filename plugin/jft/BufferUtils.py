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

	def connect_insert_text(self, handler):
		handlers = self.buffer.get_data('BufferUtilsInsertTextHandler')
		
		if handlers == None:
			id1 = self.buffer.connect('insert-text', self.on_insert_text)
			id2 = self.buffer.connect_after('insert-text', self.on_insert_text_after)
		
			self.buffer.set_data('BufferUtilsInsertTextHandler', {'ids': [id1, id2], 'handlers': [handler]})
		else:
			handlers['handlers'].append(handler)
	
	def disconnect_insert_text(self, handler):
		handlers = self.buffer.get_data('BufferUtilsInsertTextHandler')
		
		if handlers == None:
			return

		if handler in handlers['handlers']:
			del handlers['handlers'][handler]
			
			if len(handlers['handlers']) == 0:
				for i in handlers['ids']:
					self.buffer.disconnect(i)
				
				self.buffer.set_data('BufferUtilsInsertTextHandler', None)

	def __getattr__(self, name):
		return getattr(self.buffer, name)

	def on_insert_text(self, buf, location, text, length):
		self._insert_text_start = buf.create_mark(None, location, True)
	
	def on_insert_text_after(self, buf, location, text, length):
		handlers = self.buffer.get_data('BufferUtilsInsertTextHandler')

		piter = self.get_iter_at_mark(self._insert_text_start)
		
		for handler in handlers['handlers']:
			start = piter.copy()
			end = location.copy()
			
			handler(start, end)
		
		self.delete_mark(self._insert_text_start)
