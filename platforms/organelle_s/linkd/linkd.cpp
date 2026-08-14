/*
    linkd - follows an Ableton Link session and reports the beat over OSC.

    Copyright 2026.

    This program is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by the Free
    Software Foundation, either version 2 of the License, or (at your option)
    any later version. See LICENSE in this directory.

    It is a separate program on purpose. Ableton Link is GPL, EYESY_OS is BSD,
    and the only thing crossing between them is an OSC message. Nothing here is
    linked into the rest of the system, and nothing from the rest of the system
    is linked in here — the OSC encoding below is a few dozen lines rather than
    a dependency for that reason.

    Sends to the video engine on port 4000:
        /link/trig              a beat division boundary was crossed
        /link/status i i f      enabled, peer count, tempo

    Listens on port 4002:
        /link/enable i          join or leave the session
        /link/div f             beats per trigger, 0.25 is a sixteenth
*/

#include <ableton/Link.hpp>

#include <arpa/inet.h>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <sys/socket.h>
#include <unistd.h>

#define ENGINE_PORT 4000
#define LISTEN_PORT 4002

// how often the timeline is sampled. the engine only draws at 30 fps so this
// is far finer than anything downstream can use, it just keeps the boundary
// from being missed
#define POLL_US 2000

#define STATUS_INTERVAL_US 250000

// one bar of four, so a whole note lands on the bar line other Link apps agree on
#define QUANTUM 4.0

static int sock = -1;
static sockaddr_in engineAddr;
static volatile sig_atomic_t running = 1;

static void onSignal(int) { running = 0; }

/* --- just enough OSC to say what this program has to say --- */

struct OscMessage
{
  uint8_t buf[128];
  size_t n = 0;

  void pad()
  {
    while (n % 4) buf[n++] = 0;
  }

  void string(const char* s)
  {
    size_t len = strlen(s);
    if (n + len + 4 > sizeof(buf)) return;
    memcpy(buf + n, s, len);
    n += len;
    buf[n++] = 0;
    pad();
  }

  void begin(const char* address, const char* tags)
  {
    n = 0;
    string(address);
    string(tags);
  }

  void addInt(int32_t v)
  {
    if (n + 4 > sizeof(buf)) return;
    uint32_t be = htonl((uint32_t) v);
    memcpy(buf + n, &be, 4);
    n += 4;
  }

  void addFloat(float v)
  {
    uint32_t bits;
    memcpy(&bits, &v, 4);
    addInt((int32_t) bits);
  }

  void send() const
  {
    sendto(sock, buf, n, 0, (sockaddr*) &engineAddr, sizeof(engineAddr));
  }
};

// Returns the argument offset for a message whose address matches, or -1.
// Only the two shapes this program is sent are understood.
static int matchAddress(const uint8_t* p, size_t len, const char* address)
{
  size_t alen = strlen(address);
  if (len < alen + 1 || memcmp(p, address, alen) != 0 || p[alen] != 0) return -1;

  size_t off = ((alen + 1) + 3) & ~size_t(3);   // past the padded address
  if (off >= len || p[off] != ',') return -1;

  size_t tagLen = strnlen((const char*) p + off, len - off);
  off += (tagLen + 1 + 3) & ~size_t(3);         // past the padded type tags
  return off <= len ? (int) off : -1;
}

static int32_t readInt(const uint8_t* p)
{
  uint32_t be;
  memcpy(&be, p, 4);
  return (int32_t) ntohl(be);
}

static float readFloat(const uint8_t* p)
{
  uint32_t bits = (uint32_t) readInt(p);
  float v;
  memcpy(&v, &bits, 4);
  return v;
}

/* --- */

int main()
{
  signal(SIGINT, onSignal);
  signal(SIGTERM, onSignal);

  sock = socket(AF_INET, SOCK_DGRAM, 0);
  if (sock < 0)
  {
    fprintf(stderr, "linkd: no socket\n");
    return 1;
  }
  fcntl(sock, F_SETFL, O_NONBLOCK);

  sockaddr_in me{};
  me.sin_family = AF_INET;
  me.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  me.sin_port = htons(LISTEN_PORT);
  if (bind(sock, (sockaddr*) &me, sizeof(me)) < 0)
  {
    fprintf(stderr, "linkd: port %d is taken\n", LISTEN_PORT);
    return 1;
  }

  engineAddr = sockaddr_in{};
  engineAddr.sin_family = AF_INET;
  engineAddr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  engineAddr.sin_port = htons(ENGINE_PORT);

  ableton::Link link(120.0);
  bool enabled = false;
  double division = 1.0;          // beats per trigger, a quarter note
  long long lastTick = 0;
  bool haveTick = false;
  auto lastStatus = link.clock().micros();

  printf("linkd up, listening on %d, reporting to %d\n", LISTEN_PORT, ENGINE_PORT);
  fflush(stdout);

  OscMessage out;
  uint8_t in[512];

  while (running)
  {
    ssize_t len;
    while ((len = recv(sock, in, sizeof(in), 0)) > 0)
    {
      int at = matchAddress(in, (size_t) len, "/link/enable");
      if (at >= 0 && at + 4 <= len)
      {
        bool want = readInt(in + at) != 0;
        if (want != enabled)
        {
          enabled = want;
          link.enable(enabled);
          haveTick = false;       // do not fire for the gap while it was off
          printf("linkd: %s\n", enabled ? "enabled" : "disabled");
          fflush(stdout);
        }
        continue;
      }

      at = matchAddress(in, (size_t) len, "/link/div");
      if (at >= 0 && at + 4 <= len)
      {
        float d = readFloat(in + at);
        if (d > 0.0f && d <= 64.0f)
        {
          division = d;
          haveTick = false;       // re-anchor rather than firing on the change
        }
        continue;
      }
    }

    const auto now = link.clock().micros();

    if (enabled)
    {
      const auto state = link.captureAppSessionState();
      const double beat = state.beatAtTime(now, QUANTUM);
      const long long tick = (long long) std::floor(beat / division);

      if (!haveTick)
      {
        lastTick = tick;
        haveTick = true;
      }
      else if (tick != lastTick)
      {
        lastTick = tick;
        out.begin("/link/trig", ",");
        out.send();
      }
    }

    if (now - lastStatus > std::chrono::microseconds(STATUS_INTERVAL_US))
    {
      lastStatus = now;
      const auto state = link.captureAppSessionState();
      out.begin("/link/status", ",iif");
      out.addInt(enabled ? 1 : 0);
      out.addInt((int32_t) link.numPeers());
      out.addFloat((float) state.tempo());
      out.send();
    }

    usleep(POLL_US);
  }

  link.enable(false);
  close(sock);
  printf("linkd out\n");
  return 0;
}
