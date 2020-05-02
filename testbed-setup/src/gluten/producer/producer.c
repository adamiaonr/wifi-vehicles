/* producer.c : produces udp packets to be consumed by consumer app */

#include <stdio.h>      /* standard C i/o facilities */
#include <stdlib.h>     /* needed for atoi() and atof() */
//#include <unistd.h>     /* defines STDIN_FILENO, system calls, etc */
#include <sys/types.h>  /* system data type definitions */
#include <sys/socket.h> /* socket specific definitions */
#include <netinet/in.h> /* INET constants and stuff */
#include <arpa/inet.h>  /* IP address conversion stuff */
#include <netdb.h>      /* gethostbyname */
#include <string.h>
#include <time.h>
#include <sys/time.h>   /* struct timeval */
#include <signal.h>
#include <unistd.h>
#include <errno.h>

#define MAXBUF 2*1024*1024
#define PAYLOAD_SIZE 1472
#define PACKET_SIZE ((16 + 20 + 8) + PAYLOAD_SIZE)

#define TV_USEC_STR_SIZE 6
#define TV_SEC_STR_SIZE 10
// binary timestamp after str representation : 17 chars + 1 null terminating char '\0'
#define TV_BINARY_OFFSET TV_SEC_STR_SIZE + TV_USEC_STR_SIZE + 2

#ifdef ARCH_MIPS
#define SKIP_SLEEP (int) 50
#endif

// backward compatibility fix for compile error: ‘struct hostent’ has no member named ‘h_addr’
#define h_addr h_addr_list[0]

static volatile int carry_on = 1;

void handler(int dummy) {
    carry_on = 0;
}

// add timestamp to udp packet's payload:
//  - bytes [0, 16] : timestamp in str format, <tv_sec>.<tv_usec>
//  - bytes [17, 17 + sizeof(struct timeval) - 1] : timestamp in binary format, struct timeval
void add_timestamp2payload(unsigned char * payload)
{
    // get current timestamp
    struct timeval snd_timestamp;
    gettimeofday(&snd_timestamp, NULL);

    // write payload in binary and string format, so that it shows up in wireshark, i.e. '<tv_sec>.<tv_usec>'
    // - tv_usec part : 6 digits, [11, 16]
    unsigned int tv_usec = snd_timestamp.tv_usec;
    for (unsigned i = TV_USEC_STR_SIZE; i > 0; i--)
    {
        payload[i + TV_SEC_STR_SIZE] = (tv_usec % 10) + 48;
        tv_usec /= 10;
    }
    // - dot '.' : 1 char, [10]
    payload[TV_SEC_STR_SIZE] = ((unsigned) '.');
    
    // - tv_sec part : 10 digits, [0, 9]
    unsigned int tv_sec = snd_timestamp.tv_sec;    
    for (unsigned i = TV_SEC_STR_SIZE; i > 0; i--)
    {
        payload[i - 1] = (tv_sec % 10) + 48;
        tv_sec /= 10;
    }

    // copy timestamp in binary format to payload
    memcpy(&payload[TV_BINARY_OFFSET], &snd_timestamp, sizeof(struct timeval));
}

int main(int argc, char **argv) {

    int sk;
    struct sockaddr_in server;
    struct hostent * hp;

    if (argc != 4) {
        fprintf(stderr, "[ERROR] usage : %s <consumer-ip> <consumer-port> <Mbps>\n", argv[0]);
        exit(1);
    }

    // set handler for SIGINT (CNTRL+C)
    signal(SIGINT, handler);

    // create udp socket
    if ((sk = socket(PF_INET, SOCK_DGRAM, 0)) < 0) {
        perror("[ERROR] problem creating socket");
        exit(1);
    }

    // get address of server from hostname passed as arg
    // FIXME: does gethostbyname() work w/ ip addresses? shouldn't it be getaddrinfo()?
    server.sin_family = AF_INET;
    if ((hp = gethostbyname(argv[1])) == 0) {
        fprintf(stderr, "[ERROR] couldn't get host for %s\n", argv[1]);
        exit(1);
    }
    
    memcpy(&server.sin_addr.s_addr, hp->h_addr, hp->h_length);
    server.sin_port = htons(atoi(argv[2]));

    char ipv4_str[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &(server.sin_addr), ipv4_str, INET_ADDRSTRLEN);
    fprintf(stderr, "[INFO] producer sending to %s:%d\n", ipv4_str, ntohs(server.sin_port));

    // payload buffer to send over udp
    unsigned char payload[PAYLOAD_SIZE] = {0};

    int n_bytes_sent = 0;
    unsigned long byte_cntr = 0, pckt_cntr = 0;
    time_t init_time, curr_time;

#ifdef ARCH_MIPS
    int skip_sleep = SKIP_SLEEP;
#endif
    init_time = time(NULL);
    while (carry_on) {
        curr_time = time(NULL);
        if (curr_time > init_time) {

            time_t elapsed_time = curr_time - init_time;
            double bitrate = (double) (byte_cntr * 8.0) / (double) ((elapsed_time) * 1000000.0);
            // csv like stdout syntax : 
            fprintf(stdout, "%ld,%lu,%lu,%ld,%.3f\n", (long int) curr_time, pckt_cntr, byte_cntr, (long int) elapsed_time, bitrate);
            
            byte_cntr = 0;
            pckt_cntr = 0;
            init_time = curr_time;
        }

        // clear payload
        memset(payload, 0, PAYLOAD_SIZE);
        // add current timestamp to payload, in both binary and string format
        add_timestamp2payload(payload);
        // send packet
        n_bytes_sent = sendto(sk, payload, PAYLOAD_SIZE, MSG_DONTWAIT, (struct sockaddr*) &server, sizeof(server));

        // check for problems in send()
        // if (n_bytes_sent < 0) {
        //     perror("[ERROR] sendto() returned < 0");
        // }

        if (n_bytes_sent > 0) {
            byte_cntr += n_bytes_sent;
            pckt_cntr++;
        }

        // FIXME : send at max rate
#ifdef ARCH_MIPS
        // FIXME : why this?
        // the unifi ac lite (mips arch) doesn't handle usleep(1) as desired.
        // instead of sleeping for 1 us, it sleeps for longer, thus limiting throughput to 50 Mbps.
        // as such, we let it usleep for whatever period the unifi follows, but only every SKIP_SLEEP iterations.
        // this is helpful, as it doesn't keep the CPU at 100% at all times.
        if (skip_sleep < 0) {
           usleep(1);
           skip_sleep = SKIP_SLEEP;
        } else {
           skip_sleep--;
        }
#else
        usleep(10);
#endif
    }

    exit(0);
}
