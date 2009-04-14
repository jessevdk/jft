import gdata
import gnomekeyring
import gtk

class Calendar:
	def __init__(self):
		pass
		
	def login(self):
		calendar_service = gdata.calendar.service.CalendarService()
	
	def ask_credentials(self, username, handler):
		dlg = gtk.Dialog('Authentication', None, 0, 
						 (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
						  gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
		
		dlg.set_border_width(6)
		dlg.set_has_separator(False)
		hbox = gtk.HBox(False, 6)
		
		table = gtk.Table(2, 2, False)
		table.set_col_spacings(3)
		table.set_row_spacings(3)
		
		lbl = gtk.Label('Username:')
		lbl.set_alignment(0, 0.5)
		table.attach(lbl, 0, 1, 0, 1, 0, 0, 0, 0)
		
		lbl = gtk.Label('Password:')
		lbl.set_alignment(0, 0.5)
		table.attach(lbl, 0, 1, 1, 2, 0, 0, 0, 0)
		
		self.entry_username = gtk.Entry()
		table.attach(self.entry_username, 1, 2, 0, 1, gtk.FILL | gtk.EXPAND, 0, 0, 0)
		
		self.entry_passwd = gtk.Entry()
		self.entry_passwd.set_visibility(False)
		table.attach(self.entry_passwd, 1, 2, 1, 2, gtk.FILL | gtk.EXPAND, 0, 0, 0)
		
		img = gtk.Image()
		img.set_from_stock(gtk.STOCK_DIALOG_AUTHENTICATION, gtk.ICON_SIZE_DIALOG)
		
		vb = gtk.VBox(False, 6)
		lbl = gtk.Label("<i>Please provide your credentials for the\ngoogle calendar service</i>")
		lbl.set_alignment(0, 0.5)
		lbl.set_use_markup(True)
		
		vb.pack_start(lbl, False, False, 0)
		vb.pack_start(table, True, True, 0)
		
		hbox.pack_start(img, False, False, 0)
		hbox.pack_start(vb, True, True, 0)
		
		dlg.vbox.pack_start(hbox, True, True, 0)
		dlg.connect('response', self.on_authentication_response, handler)
		dlg.show_all()
	
	def get_credentials(self, username, handler):
		if username:
			try:
				items = gnomekeyring.find_network_password_sync(username, 'gmail.com', None, None, None, None, 0)
				handler(items[0]['user'], items[0]['password'])
			except gnomekeyring.NoMatchError:
				self.ask_credentials(username, handler)
		else:
			self.ask_credentials(username, handler)

	def on_authentication_response(self, dlg, response, handler):
		if response == gtk.RESPONSE_ACCEPT:
			print gnomekeyring.set_network_password_sync(None, self.entry_username.get_text(), 'gmail.com', None, None, None, None, 0, self.entry_passwd.get_text())
		else:
			handler(None, None)
		
		dlg.destroy()
