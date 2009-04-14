import gedit
from DocumentHelper import DocumentHelper
from Signals import Signals
import Constants

class WindowHelper(Signals):
	DOCUMENT_HELPER_KEY = 'DocumentHelperKey'

	def __init__(self, plugin, window):
		Signals.__init__(self)

		self._window = window
		self._plugin = plugin
		
		# Insert document helpers
		for view in window.get_views():
			self.add_document_helper(view)
		
		self.connect_signal(window, 'tab-added', self.on_tab_added)
		self.connect_signal(window, 'tab-removed', self.on_tab_removed)

	def deactivate(self):
		# Remove document helpers
		for view in self._window.get_views():
			self.remove_document_helper(view)

		self.disconnect_signals(self._window)

		self._window = None
		self._plugin = None		

	def update_ui(self):
		pass

	def add_document_helper(self, view):
		if view.get_data(Constants.DOCUMENT_HELPER_KEY) != None:
			return
		
		DocumentHelper(view)

	def remove_document_helper(self, view):
		helper = view.get_data(Constants.DOCUMENT_HELPER_KEY)
		
		if helper != None:
			helper.stop()
	
	def on_tab_added(self, window, tab):
		self.add_document_helper(tab.get_view())
	
	def on_tab_removed(self, window, tab):
		self.remove_document_helper(tab.get_view())
