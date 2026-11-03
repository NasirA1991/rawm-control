PYTHON ?= python3
PREFIX ?= /usr

.PHONY: run demo test hwtest install user-install uninstall lint-metadata clean

run:
	$(PYTHON) -m rawm_control

demo:
	$(PYTHON) -m rawm_control --demo

test:
	$(PYTHON) -m unittest discover -s tests -v

hwtest:
	RAWM_HW_TEST=1 $(PYTHON) -m unittest tests.test_hardware -v

install:
	PREFIX=$(PREFIX) ./install.sh

user-install:
	./install.sh --user

lint-metadata:
	desktop-file-validate data/io.github.rawmcontrol.RawmControl.desktop
	appstreamcli validate --no-net data/io.github.rawmcontrol.RawmControl.metainfo.xml

clean:
	rm -rf stage __pycache__ rawm_control/__pycache__ tests/__pycache__ tools/__pycache__
