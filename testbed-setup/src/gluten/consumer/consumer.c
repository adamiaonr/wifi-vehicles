/* UDP echo server program -- echo-server-udp.c */

// #include <iostream>
// #include <sstream>
// #include <fstream>  // reading .nw files

#include <stdio.h>      /* standard C i/o facilities */
#include <stdlib.h>     /* needed for atoi() */
#include <unistd.h>     /* defines STDIN_FILENO, system calls,etc */
#include <fcntl.h>      /* O_NONBLOCK */
#include <sys/types.h>  /* system data type definitions */
#include <sys/socket.h> /* socket specific definitions */
#include <netinet/in.h> /* INET constants and stuff */
#include <arpa/inet.h>  /* IP address conversion stuff */
#include <netdb.h>      /* gethostbyname */
#include <signal.h>
#include <sys/time.h>

/* this routine echos any messages (UDP datagrams) received */

#define MAXBUF 2*1024*1024

static volatile int carry_on = 1;

void handler(int dummy) {
    carry_on = 0;
}

void consumer_recv(int sd) {

    int len, n;
    char bufin[MAXBUF];
    struct sockaddr_in remote;

    len = sizeof(remote);
    unsigned long byte_cntr = 0, pckt_cntr = 0;

    time_t init_time, curr_time;
    init_time = time(NULL);

    // FIXME : non-blocking socket modifications
    // int flags = fcntl(sd, F_GETFL, 0);
    // fcntl(sd, F_SETFL, flags | O_NONBLOCK);

    while (carry_on) {

        curr_time = time(NULL);
        if (curr_time > init_time) {

            time_t elapsed_time = curr_time - init_time;
            double bitrate = (double) (byte_cntr * 8.0) / (double) ((curr_time - init_time) * 1000000.0);

            // timestamp,pckt_cntr (recvd),byte_cntr (recvd),elapsed time,bitrate (recvd)
            fprintf(stdout, "%d,%d,%d,%d,%f\n", curr_time, pckt_cntr, byte_cntr, elapsed_time, bitrate);

            byte_cntr = 0;
            pckt_cntr = 0;
            init_time = curr_time;
        }

        n = recvfrom(sd, bufin, MAXBUF, 0, (struct sockaddr *) &remote, (socklen_t *) &len);
        // n = read(sd, bufin, MAXBUF);

        if (n > 0) {
            byte_cntr += n;
            pckt_cntr++;
        } 
        // else {
        //     perror("[ERROR] server");
        // }
        // FIXME : add feedback on bit per sec        
        // if (!(n < 0)) {
        //     sendto(sd, bufin, n, 0, (struct sockaddr *) &remote, len);
        // }
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
        fprintf(stderr, "echo_server::main() : [ERROR] usage : %s <port-number>\n", argv[0]);
        exit(1);
    }

    // create udp 'listen' socket
    if ((ld = socket(PF_INET, SOCK_DGRAM, 0)) < 0) {
        fprintf(stderr, "echo_server::main() : [ERROR] problem creating socket\n");
        exit(1);
    }

    skaddr.sin_family = AF_INET;
    skaddr.sin_addr.s_addr = htonl(INADDR_ANY);
    skaddr.sin_port = htons(atoi(argv[1]));

    // bind listen socket to a fixed <ip>:<port> pair
    if (bind(ld, (struct sockaddr *) &skaddr, sizeof(skaddr)) < 0) {
        fprintf(stderr, "echo_server::main() : [ERROR] problem binding socket\n");
        exit(1);
    }

    length = sizeof(skaddr);
    if (getsockname(ld, (struct sockaddr *) &skaddr, (socklen_t *) &length) < 0) {
        fprintf(stderr, "echo_server::main() : [ERROR] getsockname() error\n");
        exit(1);
    }

    fprintf(stdout, "echo_server::main() : [INFO] echo server listening on port %d\n", ntohs(skaddr.sin_port));

    // set a recv timeout on sk
    struct timeval read_timeout;
    read_timeout.tv_sec = 2;
    read_timeout.tv_usec = 0;
    setsockopt(ld, SOL_SOCKET, SO_RCVTIMEO, &read_timeout, sizeof read_timeout);
    // // set for broadcast recv
    // int broadcast=1;
    // setsockopt(ld, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof broadcast);

    consumer_recv(ld);

    exit(0);
}
