/* echo-client-udp.c */

/* Simple UDP echo client - tries to send everything read from stdin
   as a single datagram (MAX 1MB)*/

#include <iostream>
#include <vector>
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
#include <string.h>
#include <sys/time.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>

struct echo_record {
    struct timeval timestamp;
};

#define PACKET_SIZE (unsigned int) ((16 + 20 + 8) + sizeof(struct echo_record))
#define MAXBUF 10*1024

static volatile int carry_on = 1;

void handler(int dummy) {
    carry_on = 0;
}

int main(int argc, char **argv) {

    int sk;
    struct sockaddr_in server;
    struct hostent * hp;
    char buf[MAXBUF];
    int buf_len;
    int n_sent;
    int n_read;

    if (argc != 5) {
        std::cerr << "echo_client::main() : [ERROR] usage : " << argv[0] << " <server-ip> <port-number> <bps> <output-dir>" << std::endl;
        exit(1);
    }

    // set handler for SIGINT (CNTRL+C)
    signal(SIGINT, handler);

    // files w/ seq. packet seq. numbers
    std::vector<std::ofstream> files = std::vector<std::ofstream> (2);
    std::string filenames[2] = {"sent.tsv", "rcvd.tsv"};
    for (unsigned int i = 0; i < files.size(); i++) {
        files[i].open(std::string(argv[4]) + std::string("/") + filenames[i]);
        files[i] << "timestamp\n";
    }

    // create udp socket
    if ((sk = socket(PF_INET, SOCK_DGRAM, 0)) < 0) {
        std::cerr << "echo_client::main() : [ERROR] problem creating socket" << std::endl;
        exit(1);
    }


    // get address of server from hostname passed as arg
    // FIXME: does gethostbyname() work w/ ip addresses? shouldn't it be getaddrinfo()?
    server.sin_family = AF_INET;
    if ((hp = gethostbyname(argv[1])) == 0) {
        std::cerr << "echo_client::main() : [ERROR] couldn't get host for " << argv[1] << std::endl;
        exit(1);
    }
    
    // copy address got by gethostname() into sockaddr_in struct    
    memcpy(&server.sin_addr.s_addr, hp->h_addr, hp->h_length);
    // set port in sockaddr_in struct
    server.sin_port = htons(atoi(argv[2]));

    // send udp packet w/ timestamp as payload
    struct echo_record * payload = (struct echo_record *) buf;

    // set a recv timeout on sk
    struct timeval read_timeout, s, e;
    read_timeout.tv_sec = 1;
    read_timeout.tv_usec = 0;
    setsockopt(sk, SOL_SOCKET, SO_RCVTIMEO, &read_timeout, sizeof read_timeout);

    // # of bytes sent
    unsigned long int bytes_sent = 0;
    double interval = (((double) (PACKET_SIZE * 8.0)) / ((double) std::stof(argv[3]))) * 1000000.0;
    std::cout << "echo_client::main() : [INFO] sleep interval for bw " << std::stof(argv[3]) << " bps : " << interval << " us" << std::endl;

    gettimeofday(&s, NULL);
    while (carry_on) {

        gettimeofday(&(payload->timestamp), NULL);
        buf_len = sizeof(struct echo_record);
        n_sent = sendto(sk, buf, buf_len, MSG_DONTWAIT, (struct sockaddr*) &server, sizeof(server));
        // std::cout << "echo_client::main() : [INFO] sent : " << (int) payload->timestamp.tv_sec << "." << (int) payload->timestamp.tv_usec << std::endl;

        // check for problems in send()
        if (n_sent < 0) {
            std::cerr << "echo_client::main() : [ERROR] sendto() returned < 0" << std::endl;
            exit(1);
        }

        if (n_sent != buf_len) {
            std::cout << "echo_client::main() : [INFO] sendto() sent " << n_sent << " byte (vs. " << buf_len << ")" << std::endl;
        }

        // save timestamp on 'sent' file
        files[0] << payload->timestamp.tv_sec << "." << payload->timestamp.tv_usec << "\n";

        // block till the echo response is given
        n_read = recvfrom(sk, buf, MAXBUF, 0, NULL, NULL);
        if (n_read < 0) {

            int errsv = errno;
            if (!((errsv == EWOULDBLOCK) || (errsv == EAGAIN))) {
                std::cerr << "echo_client::main() : [ERROR] recvfrom() returned < 0" << std::endl;
                exit(1);
            }
        }

        // extract payload from response & save it to file
        struct echo_record * echo_response = (struct echo_record *) buf;
        // save timestamp on 'sent' file
        files[1] << echo_response->timestamp.tv_sec << "." << echo_response->timestamp.tv_usec << "\n";
        // std::cout << "echo_client::main() : [INFO] got : " << (int) echo_response->timestamp.tv_sec << "." << (int) echo_response->timestamp.tv_usec << std::endl;

        // FIXME: this should be adjustable by an arg
        usleep(interval);

        // FIXME: overflow problems ahead?
        bytes_sent += (((16 + 20 + 8)) + (sizeof(struct echo_record)));
    }

    gettimeofday(&e, NULL);

    std::cout << "echo_client::main() : [INFO] payload size : " << (sizeof(struct echo_record) * 8) << " bit (" << sizeof(struct echo_record) << " byte)" << std::endl;
    std::cout << "echo_client::main() : [INFO] packet size : " << (PACKET_SIZE * 8) << " bit (" << PACKET_SIZE << " byte)" << std::endl;
    double time_elapsed = (e.tv_sec - s.tv_sec) + ((e.tv_usec - s.tv_usec) / 1000000.0);
    std::cout << "echo_client::main() : [INFO] time elapsed : " << time_elapsed << " sec" << std::endl;
    std::cout << "echo_client::main() : [INFO] avg. sleep time : " << time_elapsed / ((double) bytes_sent / (double) PACKET_SIZE) << " sec" << std::endl;
    std::cout << "echo_client::main() : [INFO] avg. bit rate : " 
        << (double) (bytes_sent * 8) / (time_elapsed) << " bps (" 
        << (double) (bytes_sent) / (time_elapsed) << " B(byte) ps)" << std::endl;

    files[0].close();
    files[1].close();

    // add report file
    std::ofstream report;
    report.open(std::string(argv[4]) + std::string("/report.tsv"));
    report << "payload\tpacket\ttime elapsed\tavg sleep time\tavg bitrate\n";
    report << (sizeof(struct echo_record) * 8) << "\t" << (PACKET_SIZE * 8) << "\t" << time_elapsed << "\t" << time_elapsed / ((double) bytes_sent / (double) PACKET_SIZE) << "\t" << (double) (bytes_sent * 8) / (time_elapsed) << "\n";
    report.close();

    exit(0);
}
