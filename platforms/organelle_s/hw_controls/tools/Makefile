# Desktop preview of the OLED pages. Builds without wiringPi so it runs on a
# laptop as well as on the device.
#
#   make -f tools/Makefile
#   ./oled_preview /tmp/oled
#   python3 tools/oled_view.py /tmp/oled*.raw -o /tmp/oled.png

CXX ?= g++
CXXFLAGS += -std=c++11 -Wall

oled_preview : tools/oled_preview.cpp OledScreen.cpp OledPages.cpp
	$(CXX) $(CXXFLAGS) -o oled_preview tools/oled_preview.cpp OledScreen.cpp OledPages.cpp

.PHONY : clean
clean :
	rm -f oled_preview
