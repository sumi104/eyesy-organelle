# linkd needs the Ableton Link headers, which are not vendored here: Link is
# GPL and the rest of this tree is BSD, so it stays a separate download feeding
# a separate binary.
#
#     git clone --recurse-submodules https://github.com/Ableton/link ~/link
#     make
#
# Point LINK_DIR somewhere else if it is not in ~/link.

LINK_DIR ?= $(HOME)/link

CXX ?= g++

# Link needs C++17. It used to build as C++11 and a lot of writing about it
# still says so, but the current version uses std::invoke_result_t.
CXXFLAGS += -std=c++17 -O2 -Wall
CPPFLAGS += -I$(LINK_DIR)/include -I$(LINK_DIR)/modules/asio-standalone/asio/include
CPPFLAGS += -DASIO_STANDALONE

UNAME := $(shell uname -s)
ifeq ($(UNAME),Darwin)
    CPPFLAGS += -DLINK_PLATFORM_MACOSX=1
else
    CPPFLAGS += -DLINK_PLATFORM_LINUX=1
    LDLIBS += -lpthread -latomic
endif

default : linkd

linkd : linkd.cpp
	@test -f "$(LINK_DIR)/include/ableton/Link.hpp" || { \
	  echo "no Link headers at $(LINK_DIR)"; \
	  echo "  git clone --recurse-submodules https://github.com/Ableton/link $(LINK_DIR)"; \
	  exit 1; }
	@# cloning without --recurse-submodules leaves this empty and the failure
	@# is a page of template errors that never mentions the submodule
	@test -f "$(LINK_DIR)/modules/asio-standalone/asio/include/asio.hpp" || { \
	  echo "Link is at $(LINK_DIR) but its asio submodule is missing"; \
	  echo "  git -C $(LINK_DIR) submodule update --init --recursive"; \
	  exit 1; }
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -o $@ $< $(LDLIBS)

.PHONY : clean
clean :
	rm -f linkd
