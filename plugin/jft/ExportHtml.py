from ExportLatex import ExportLatex
import os

class ExportHtml:
	def __init__(self, data, filename):
		self._exporter = ExportLatex(data, filename)
		self._filename = filename
	
	def export(self):
		if self._exporter.export():
			filename = self._exporter.filename_tex()
			
			os.system('latex2html -split 0 "%s"' % (filename, ))
			return True
		else:
			return False
	
	def show(self):
		dd = self._exporter.filename_ext()
		
		os.system('gnome-open "%s/index.html"' % (dd,))
