Description:
------------------------
Netperf is a benchmark that can be used to measure the performance of
many different types of networking. It provides tests for both
unidirectional throughput, and end-to-end latency.

Inputs Needed To Run Tests:
-----------------------------
interface		- test interface name eth2 or mac addr 02:5d:c7:xx:xx:03
PEERIP			- IP of the Peer interface to be tested
PEERUSER		- Username in Peer system to be used
Iface			- interface on which test run
NETSERVER_RUN		- Whether to run netserver in peer or not (1 to run, 0 to not run)
EXPECTED_THROUGHPUT	- Expected Throughput as a percentage (1-100)
netperf_download	- User has the option to choose download location for netperf tool.
duration		- duration to run each test (sec) 
minimum_iterations	- minimum iterations when trying to reach certain confidence levels
maximum_iterations	- maximum iterations when trying to reach certain confidence levels
option			- test and supporting parameters
host-IP                 - Specify host-IP for ip configuration.
netmask                 - specify netmask for ip configuration.

Requirements:
-----------------------
1.Generate sshkey for your test partner to run the test uninterrupted.
2.install nteifaces using pip.
command: pip install netifaces
3.user should have root access to both client machine and peer machine.

Additional Notes:
-----------------
Currently "Netserver" supports only for IPv4/AF_INET Ports,
where Netserver initialize and listens on IPV4 interfaces for both Host and Peer systems.

