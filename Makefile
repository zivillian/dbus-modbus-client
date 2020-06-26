FILES =									\
	dbus-modbus-client.py						\
	carlo_gavazzi.py						\
	device.py							\
	ev_charger.py							\
	mdns.py								\
	probe.py							\
	register.py							\
	scan.py								\
	smappee.py							\
	utils.py							\

VELIB =									\
	settingsdevice.py						\
	ve_utils.py							\
	vedbus.py							\

all:

install:
	install -d $(DESTDIR)$(bindir)
	install -m 0644 $(FILES) $(DESTDIR)$(bindir)
	install -m 0644 $(addprefix ext/velib_python/,$(VELIB)) \
		$(DESTDIR)$(bindir)
	chmod +x $(DESTDIR)$(bindir)/$(firstword $(FILES))

clean distclean:

testinstall:
	$(eval TMP := $(shell mktemp -d))
	$(MAKE) DESTDIR=$(TMP) install
	(cd $(TMP) && ./dbus-modbus-client.py --help > /dev/null)
	-rm -rf $(TMP)
