#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <unistd.h>

/* The app passes a pidfd for itself. Unlike parent-PID polling, it cannot
 * accidentally attach to a reused PID. This thread also runs while paused. */
static int owner_fd;
static void *watch_owner(void *unused) {
    (void)unused;
    struct pollfd owner = {.fd = owner_fd, .events = POLLIN};
    int result;
    do { result = poll(&owner, 1, -1); } while (result < 0 && errno == EINTR);
    close(owner_fd);
    kill(getpid(), SIGINT);
    /* Give the muxer time to finish, but never leave an orphan capturing. */
    for (int i = 0; i < 25; ++i) sleep(1);
    kill(getpid(), SIGKILL);
    return NULL;
}

__attribute__((constructor)) static void start_guard(void) {
    const char *value = getenv("OMNISHOT_RECORD_OWNER_FD");
    if (!value) return;
    char *end;
    long fd = strtol(value, &end, 10);
    if (*end || fd < 3 || fd > 1048576 || fcntl((int)fd, F_SETFD, FD_CLOEXEC) < 0) _exit(125);
    owner_fd = (int)fd;
    /* Descendant executables must not start a second guard for this fd. */
    unsetenv("OMNISHOT_RECORD_OWNER_FD");
    value = getenv("OMNISHOT_RECORD_LIBRARY_FD");
    if (value) {
        fd = strtol(value, &end, 10);
        if (*end || fd < 3 || fd > 1048576) _exit(125);
        char prefix[64];
        snprintf(prefix, sizeof(prefix), "/proc/self/fd/%ld", fd);
        const char *preload = getenv("LD_PRELOAD");
        if (preload && !strncmp(preload, prefix, strlen(prefix))) {
            const char *rest = preload + strlen(prefix);
            if (*rest == ':') setenv("LD_PRELOAD", rest + 1, 1);
            else if (!*rest) unsetenv("LD_PRELOAD");
        }
        close((int)fd);
        unsetenv("OMNISHOT_RECORD_LIBRARY_FD");
    }
    value = getenv("OMNISHOT_RECORD_LEASE_FD");
    if (value) {
        fd = strtol(value, &end, 10);
        if (*end || fd < 3 || fd > 1048576 || fcntl((int)fd, F_SETFD, FD_CLOEXEC) < 0) _exit(125);
        unsetenv("OMNISHOT_RECORD_LEASE_FD");
    }
    pthread_t thread;
    if (pthread_create(&thread, NULL, watch_owner, NULL)) _exit(125);
    pthread_detach(thread);
}
