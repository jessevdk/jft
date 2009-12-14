# -*- coding: utf-8-*-

import re
import os
import glob

class Parser:
	def __init__(self, exporter):
		self._exporter = exporter
		self.inline = False
	
	def parse(self, line, continuation):
		return line
	
	def end(self, line):
		return True
	
	def last(self):
		return False

class ParserComment(Parser):
	def __init__(self, exporter):
		Parser.__init__(self, exporter)
		
		self._re = re.compile('^(\s*)#(.*)')

	def parse(self, line, continuation):
		match = self._re.match(line)
		
		if match:
			return '%s%%%s' % (match.group(1), match.group(2))
		else:
			return False

class ParserMath(Parser):
	def __init__(self, exporter):
		Parser.__init__(self, exporter)
		
		self._re = re.compile('^\s*[$]([^$]*)[$]\s*$')
	
	def parse(self, line, continuation):
		match = self._re.match(line)

		if not match:
			return False
		
		return "\\begin{displaymath}\n%s\n\\end{displaymath}" % (match.group(1),)
	
class ParserList(Parser):
	def __init__(self, exporter):
		Parser.__init__(self, exporter)
		
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
	def __init__(self, exporter):
		Parser.__init__(self, exporter)

		self._re = re.compile('^\s*(%+)\s*(.*)$')
		self._re_title = re.compile('^\s*{{\s*title\s*:\s*(.*?)}}\s*$')
		self._level = 0
		self._output = ''
	
	def parse(self, line, continuation):
		match = self._re.match(line)
		
		if not match:
			return False
		
		level = len(match.group(1))
		title = self._re_title.match(match.group(2))
		
		if level == 1 and title:
			self._exporter.set_title(title.group(1))
			return True
		
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
		if self._level <= 0:
			return True

		out = '\%s{%s}' % (self.level_to_name(), self._output)
		self._output = ""
		
		return out

class ExportLatex:
	def __init__(self, data, filename):
		self._data = data
		self._filename = filename

		self._re_ext = re.compile('^(.*)\\.[^/.]*$')
		self._re_math = re.compile('[$][^$]*[$]')
		
		self._inline_parsers = [
			[re.compile('\{\{cite\((.*?)\):.*?\}\}'), self._inline_cite],
			[re.compile('([^\s].*)#'), self._inline_comment],
			[re.compile('\'([^\']+)\''), self._inline_emphasize, False],
			[re.compile('(?:[^\\]|^)_([a-z0-9- ]+)_'), self._inline_strong, False],
		]
	
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
	
	def set_title(self, title):
		if title:
			self._title = str(title)
		else:
			self._title = ''
	
	def _inline_emphasize(self, match):
		return '\\textit{%s}' % (match.group(1),)

	def _inline_strong(self, match):
		return '\\textbf{%s}' % (match.group(1),)
	
	def _inline_comment(self, match):
		return '%%%s' % (match.group(1),)
	
	def _inline_cite(self, match):
		self._citations = True
		return "\\cite{%s}" % (match.group(1).replace('_', u"¬"),)
	
	def _parse_inline_real(self, part):
		for item in self._inline_parsers:			
			while True:
				match = item[0].search(part)
				
				if not match:
					break

				part = part[:match.start(0)] + item[1](match) + part[match.end(0):]
		
		replacements = {
			'_': '\\_',
			'<=': '$\leq$',
			'>=': '$\geq$',
			'<': '$<$',
			'>': '$>$'
		}
		
		for k in replacements:
			part = part.replace(k, replacements[k])

		return part
	
	def _parse_inline(self, line):
		ret = ''
		
		while True:
			match = self._re_math.search(line)
			
			if not match:
				break
			
			ret += self._parse_inline_real(line[:match.start(0)]) + match.group(0)
			line = line[match.end(0):]

		ret += self._parse_inline_real(line)
		return ret.replace(u"¬", '_')
	
	def append(self, line):
		if isinstance(line, str) or isinstance(line, unicode):
			self._output.append(line)
		elif isinstance(line, list):
			self._output.extend(line)
	
	def export(self):
		self._output = []
		self._title = ''
		self._citations = False

		parsers = [
			ParserComment(self), 
			ParserMath(self), 
			ParserList(self), 
			ParserHeader(self), 
			Parser(self)]
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
		header = "\\title{%s}\n\n\\begin{document}\n" % (self._title,)
		packages = "\\documentclass{article}\n\\usepackage{amsmath}\n\\usepackage{fullpage}\n\\usepackage{graphicx}\n"
		
		if self._title and self._title != '':
			header += "\n\\maketitle\n\n"
		
		if self._citations:
			# Find references
			packages += "\\usepackage{apacite}\n"

			dname = os.path.dirname(self._filename)
			refiles = glob.glob(dname + "/*.bib")
			
			if refiles:
				content += "\n\\bibliographystyle{apacite}"
		
			for f in refiles:
				content += "\n\\bibliography{%s}\n" % (os.path.basename(f).replace('.bib', ''),)
		

		footer = "\\end{document}"
		
		file(self.filename_tex(), 'w').write(packages + header + content + footer)
		return True

	def show(self):
		os.system('rubber --inplace -d "%s" && gnome-open "%s"' % (self.filename_tex(), self.filename_pdf()))
