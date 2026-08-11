CXX = g++

CXXFLAGS += -std=c++11

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

default : $(objects) hw_interfaces/CM3GPIO.o
	g++ -o controls $(objects) hw_interfaces/CM3GPIO.o -l wiringPi 

.PHONY : clean

clean :
	rm -f controls oled_preview $(objects) hw_interfaces/CM3GPIO.o

# Generate with g++ -MM *.c* OSC/*.*
main.o: main.cpp OSC/OSCMessage.h OSC/OSCData.h OSC/OSCTiming.h \
 OSC/SimpleWriter.h OSC/SimpleWriter.h UdpSocket.h Socket.h Timer.h \
 OledScreen.h OledPages.h
OledScreen.o: OledScreen.cpp OledScreen.h fonts.h
OledPages.o: OledPages.cpp OledPages.h OledScreen.h
Socket.o: Socket.cpp Socket.h
Timer.o: Timer.cpp Timer.h
UdpSocket.o: UdpSocket.cpp UdpSocket.h Socket.h
OSCData.o: OSC/OSCData.cpp OSC/OSCData.h OSC/OSCTiming.h
OSCData.o: OSC/OSCData.h OSC/OSCTiming.h
OSCMatch.o: OSC/OSCMatch.c OSC/OSCMatch.h
OSCMatch.o: OSC/OSCMatch.h
OSCMessage.o: OSC/OSCMessage.cpp OSC/OSCMessage.h OSC/OSCData.h \
 OSC/OSCTiming.h OSC/SimpleWriter.h OSC/OSCMatch.h
OSCMessage.o: OSC/OSCMessage.h OSC/OSCData.h OSC/OSCTiming.h \
 OSC/SimpleWriter.h
OSCTiming.o: OSC/OSCTiming.cpp OSC/OSCTiming.h
OSCTiming.o: OSC/OSCTiming.h
SimpleWriter.o: OSC/SimpleWriter.cpp OSC/SimpleWriter.h
SimpleWriter.o: OSC/SimpleWriter.h
