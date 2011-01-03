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

	def create_mark_range(self, start, end, switched = False):
		return (self.create_mark(None, start, not switched),
				self.create_mark(None, end, switched))

	def delete_mark_range(self, r):
		ret = []

		for i in r:
			ret.append(self.get_iter_at_mark(i))
			self.delete_mark(i)

		return ret

	def iter_skip_space(self, piter):
		while True:
			c = piter.get_char()

			if not c.isspace() or c in ["\n", "\0"]:
				return

			piter.forward_char()

	def _do_block_insert_text(self, handler, block):
		handlers = self.buffer.get_data('BufferUtilsInsertTextHandler')

		if handlers and handler in handlers['handlers']:
			handlers['handlers'][handler] = not block

	def block_insert_text(self, handler):
		self._do_block_insert_text(handler, True)

	def unblock_insert_text(self, handler):
		self._do_block_insert_text(handler, False)

	def connect_insert_text(self, handler):
		handlers = self.buffer.get_data('BufferUtilsInsertTextHandler')

		if handlers == None:
			id1 = self.buffer.connect('insert-text', self.on_insert_text)
			id2 = self.buffer.connect_after('insert-text', self.on_insert_text_after)

			self.buffer.set_data('BufferUtilsInsertTextHandler', {'ids': [id1, id2], 'handlers': {handler: True}})
		else:
			handlers['handlers'][handler] = True

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
		self.begin_user_action()
		self._insert_text_start = buf.create_mark(None, location, True)

	def on_insert_text_after(self, buf, location, text, length):
		handlers = self.buffer.get_data('BufferUtilsInsertTextHandler')

		other = buf.create_mark(None, location, False)

		for handler in handlers['handlers']:
			if handlers['handlers'][handler]:
				start = self.get_iter_at_mark(self._insert_text_start)
				end = self.get_iter_at_mark(other)

				handler(start, end)

				if self._insert_text_start.get_deleted() or other.get_deleted():
					break

		if not self._insert_text_start.get_deleted():
			self.delete_mark(self._insert_text_start)

		if not other.get_deleted():
			location.assign(self.get_iter_at_mark(other))
			self.delete_mark(other)

		self.end_user_action()
