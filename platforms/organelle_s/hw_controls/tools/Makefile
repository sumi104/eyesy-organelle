# Desktop preview of the OLED pages. Builds without wiringPi so it runs on a
# laptop as well as on the device.
#
# Layout, as a contact sheet:
#
#   make -f tools/Makefile
#   ./oled_preview /tmp/oled
#   python3 tools/oled_view.py /tmp/oled*.raw -o /tmp/oled.png
#
# Speed, as something you can watch:
#
#   make -f tools/Makefile oled_anim
#   ./oled_anim /tmp/anim
#   python3 tools/oled_view.py --html /tmp/anim.html /tmp/anim*.raw

CXX ?= g++
CXXFLAGS += -std=c++11 -Wall

# A Mac with MacPorts on the path finds its g++ before anything else, and that
# one cannot find the system C++ headers - the build dies on <string>. Point
# clang at the SDK instead so a bare make works here as well as on the device.
# An explicit make CXX=... still wins, command line beats this.
ifeq ($(shell uname -s),Darwin)
CXX := clang++
SDK := $(shell xcrun --show-sdk-path)
CXXFLAGS += -isysroot $(SDK) -cxx-isystem $(SDK)/usr/include/c++/v1
endif

all : oled_preview oled_anim

oled_preview : tools/oled_preview.cpp OledScreen.cpp OledPages.cpp
	$(CXX) $(CXXFLAGS) -o oled_preview tools/oled_preview.cpp OledScreen.cpp OledPages.cpp

oled_anim : tools/oled_anim.cpp OledScreen.cpp OledPages.cpp
	$(CXX) $(CXXFLAGS) -o oled_anim tools/oled_anim.cpp OledScreen.cpp OledPages.cpp

.PHONY : all clean
clean :
	rm -f oled_preview oled_anim
