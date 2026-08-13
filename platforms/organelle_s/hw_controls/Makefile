CXX = g++

# -MMD -MP makes the compiler write out what each object actually included,
# next to the object as a .d file, which is pulled back in below. The hand
# maintained list this replaces had drifted: the OSC rules named targets
# without their directory, so they matched nothing that gets built, and
# hw_interfaces/CM3GPIO.o had no rule at all. Editing any of those headers
# left the old object files in place, and only the make clean in install.sh
# was hiding it.
CXXFLAGS += -std=c++11 -MMD -MP
CFLAGS += -MMD -MP

objects =  \
	main.o \
	Timer.o \
	OledScreen.o \
	OledPages.o \
	UdpSocket.o \
	Socket.o \
	OSC/OSCData.o \
	OSC/OSCMatch.o \
	OSC/OSCMessage.o \
	OSC/OSCTiming.o \
	OSC/SimpleWriter.o

gpio = hw_interfaces/CM3GPIO.o

deps = $(objects:.o=.d) $(gpio:.o=.d)

default : $(objects) $(gpio)
	g++ -o controls $(objects) $(gpio) -l wiringPi

.PHONY : clean

clean :
	rm -f controls oled_preview $(objects) $(gpio) $(deps)

# nothing to include on the first build, everything gets compiled anyway
-include $(deps)
