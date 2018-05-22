/* UDP echo server program -- echo-server-udp.c */

#include <iostream>
#include <sstream>
#include <fstream>  // reading .nw files

#include <stdio.h>      /* standard C i/o facilities */
#include <stdlib.h>     /* needed for atoi() */
#include <unistd.h>     /* defines STDIN_FILENO, system calls,etc */
#include <sys/types.h>  /* system data type definitions */
#include <sys/socket.h> /* socket specific definitions */
#include <netinet/in.h> /* INET constants and stuff */
#include <arpa/inet.h>  /* IP address conversion stuff */
#include <netdb.h>      /* gethostbyname */
#include <signal.h>

/* this routine echos any messages (UDP datagrams) received */

#define MAXBUF 1024*1024

static volatile int carry_on = 1;

void handler(int dummy) {
    carry_on = 0;
}

void echo(int sd) {

    int len, n;
    char bufin[MAXBUF];
    struct sockaddr_in remote;

    len = sizeof(remote);

    while (carry_on) {

        n = recvfrom(sd, bufin, MAXBUF, 0, (struct sockaddr *) &remote, (socklen_t *) &len);
        
        if (!(n < 0)) {
            sendto(sd, bufin, n, 0, (struct sockaddr *) &remote, len);
        }
    }
}

/* server main routine */
int main(int argc, char **argv) {

    int ld;
    struct sockaddr_in skaddr;
    int length;

    // set handler for SIGINT (CNTRL+C)
    signal(SIGINT, handler);

    if (argc != 2) {
        std::cerr << "echo_server::main() : [ERROR] usage : " << argv[0] << " <port-number>" << std::endl;
        exit(1);
    }

    // create udp 'listen' socket
    if ((ld = socket(PF_INET, SOCK_DGRAM, 0)) < 0) {
        std::cerr << "echo_server::main() : [ERROR] problem creating socket" << std::endl;
        exit(1);
    }

    skaddr.sin_family = AF_INET;
    skaddr.sin_addr.s_addr = htonl(INADDR_ANY);
    skaddr.sin_port = htons(atoi(argv[1]));

    // bind listen socket to a fixed <ip>:<port> pair
    if (bind(ld, (struct sockaddr *) &skaddr, sizeof(skaddr)) < 0) {
        std::cerr << "echo_server::main() : [ERROR] problem binding socket" << std::endl;
        exit(1);
    }

    length = sizeof(skaddr);
    if (getsockname(ld, (struct sockaddr *) &skaddr, (socklen_t *) &length) < 0) {
        std::cerr << "echo_server::main() : [ERROR] getsockname() error" << std::endl;
        exit(1);
    }

    std::cout << "echo_server::main() : [INFO] echo server listening on port " << ntohs(skaddr.sin_port) << std::endl;

    // set a recv timeout on sk
    struct timeval read_timeout;
    read_timeout.tv_sec = 1;
    read_timeout.tv_usec = 0;
    setsockopt(ld, SOL_SOCKET, SO_RCVTIMEO, &read_timeout, sizeof read_timeout);

    echo(ld);
    exit(0);
}