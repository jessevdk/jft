import re
import os

class Parser:
	def __init__(self):
		self.inline = False
	
	def parse(self, line, continuation):
		return line
	
	def end(self, line):
		return True
	
	def last(self):
		return False

class ParserComment(Parser):
	def __init__(self):
		Parser.__init__(self)
		
		self._re = re.compile('^(\s*)#(.*)')

	def parse(self, line, continuation):
		match = self._re.match(line)
		
		if match:
			return '%s%%%s' % (match.group(1), match.group(2))
		else:
			return False

class ParserMath(Parser):
	def __init__(self):
		Parser.__init__(self)
		
		self._re = re.compile('^\s*[$]([^$]*)[$]\s*$')
	
	def parse(self, line, continuation):
		match = self._re.match(line)

		if not match:
			return False
		
		return "\\begin{displaymath}\n%s\n\\end{displaymath}" % (match.group(1),)
	
class ParserList(Parser):
	def __init__(self):
		Parser.__init__(self)
		
		self._re = re.compile('^\s*(\*+)\s*(.*)')
		self._re_indent = re.compile('^\s*')

		self._level = 0
	
	def _push_level(self, level):
		out = ''
		
		while self._level < level:
			out += "%s\\begin{itemize}\n" % (self._level * "\t",)
			self._level += 1
		
		return out
	
	def _pop_level(self, level):
		out = ''
		
		while self._level > level:
			out += "%s\\end{itemize}\n" % ((self._level - 1) * "\t",)
			self._level -= 1
		
		return out
	
	def parse(self, line, continuation):
		match = self._re.match(line)
		
		if not match:
			return False
		
		level = len(match.group(1))
		out = self._push_level(level) + self._pop_level(level)
	
		# Append new item
		out += "%s\\item %s" % ("\t" * level, match.group(2),)
		
		return out
	
	def end(self, line):
		# If the indentation matches we kind of keep going
		match = self._re_indent.match(line)
		level = match.group(0).count("\t")
		
		if level != self._level:
			return self._pop_level(0)
		else:
			return False
	
	def last(self):
		return self._pop_level(0)

class ParserHeader(Parser):
	def __init__(self):
		Parser.__init__(self)

		self._re = re.compile('^\s*(%+)\s*(.*)$')
		self._level = 0
		self._output = ''
	
	def parse(self, line, continuation):
		match = self._re.match(line)
		
		if not match:
			return False
		
		level = len(match.group(1))
		
		if continuation and level != self._level:
			out = self.end()
			self._output = match.group(2)
		else:
			self._output += match.group(2) + " "
			out = True
		
		self._level = level
		return out
	
	def level_to_name(self):
		if self._level == 2:
			return 'subsection'
		elif self._level == 3:
			return 'subsubsection'
		else:
			return 'section'
	
	def end(self, line):
		out = '\%s{%s}' % (self.level_to_name(), self._output)
		self._output = ""
		
		return out

class ExportLatex:
	def __init__(self, data, filename):
		self._data = data
		self._filename = filename

		self._re_ext = re.compile('^(.*)\\.[^/.]*$')
		self._re_math = re.compile('[$][^$]*[$]')
		
		self._inline_parsers = {
			re.compile('\'([^\']+)\''): self._inline_emphasize,
			re.compile('_([a-z0-9- ]+)_'): self._inline_strong,
			re.compile('([^\s].*)#'): self._inline_comment,
		}
	
	def filename_ext(self, ext = None):
		# Generate filename
		m = self._re_ext.match(self._filename)
		
		if m:
			if ext:
				return m.group(1) + '.' + ext
			else:
				return m.group(1)
		else:
			return self._filename + '.' + ext
	
	def filename_tex(self):
		return self.filename_ext('tex')
		
	def filename_pdf(self):
		return self.filename_ext('pdf')
	
	def _inline_emphasize(self, match):
		return '\\textit{%s}' % (match.group(1),)

	def _inline_strong(self, match):
		return '\\textbf{%s}' % (match.group(1),)
	
	def _inline_comment(self, match):
		return '%%%s' % (match.group(1),)
	
	def _parse_inline_real(self, part):
		for parser in self._inline_parsers:
			while True:
				match = parser.search(part)
				
				if not match:
					break

				part = part[:match.start(0)] + self._inline_parsers[parser](match) + part[match.end(0):]
		
		return part.replace('_', '\_')
	
	def _parse_inline(self, line):
		ret = ''
		
		while True:
			match = self._re_math.search(line)
			
			if not match:
				break
			
			ret += self._parse_inline_real(line[:match.start(0)]) + match.group(0)
			line = line[match.end(0) + 1:]

		ret += self._parse_inline_real(line)
		return ret
	
	def append(self, line):
		if isinstance(line, str):
			self._output.append(line)
		elif isinstance(line, list):
			self._output.extend(line)
	
	def export(self):
		self._output = []
		parsers = [ParserComment(), ParserMath(), ParserList(), ParserHeader(), Parser()]
		last_parser = []

		for line in self._data.split("\n"):
			line = self._parse_inline(line)

			for parser in parsers:
				ret = parser.parse(line, parser == last_parser)
				
				if ret != False:
					if not parser in last_parser:
						for p in list(last_parser):
							r = p.end(line)
						
							if r != False:
								self.append(r)
								last_parser.remove(p)
				
					self.append(ret)
					
					if not parser in last_parser:
						last_parser.append(parser)

					break

		for parser in parsers:
			self.append(parser.last())

		content = "\n".join(self._output)		
		header = "\\documentclass{article}\n\\usepackage{amsmath}\n\\usepackage{fullpage}\n\n\\begin{document}\n"
		footer = "\\end{document}"
		
		file(self.filename_tex(), 'w').write(header + content + footer)
		return True

	def show(self):
		os.system('rubber --inplace -d "%s" && gnome-open "%s"' % (self.filename_tex(), self.filename_pdf()))
