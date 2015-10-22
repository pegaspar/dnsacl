# (c) 2015, Peter Gaspar, pegaspar@cisco.com

# ------- begin of configuration settings ---------

hostList=['bleh.cisco.com','dnspython.org','google.com','www.facebook.com']
aclName="REDIRECT"

RouterIP="192.168.182.10"
RouterUser="pegaspar"
RouterPassword="Cisco123"
defaultTTL=180
maxACLLines=20
refreshInterval=60

# certificate files
CertDirectory=''
CACertFile = 'CAcert.pem'
ClientKeyFile = 'nopassclientkey.pem' # should be private key without pass phrase to avoid prompt
ClientCertFile = 'clientcert.pem'

# ------- end of configuration settings ---------

import time
import dns.resolver
from onep.element.NetworkApplication import NetworkApplication
from onep.element import SessionConfig
from onep.vty import VtyService


class IPAttributes:
    ttl = defaultTTL
    insertedAt = 0

resolvedIPs={}

networkApplication=NetworkApplication.get_instance()
networkApplication.name = "DNSACL"

ne = networkApplication.get_network_element(RouterIP)

session_config = SessionConfig(SessionConfig.SessionTransportMode.TLS)
session_config.ca_certs = CertDirectory+CACertFile
session_config.keyfile = CertDirectory+ClientKeyFile
session_config.certfile = CertDirectory+ClientCertFile

while True:

    currentTime=time.time()

    #update the list with new IPs or new TTLs
    for host in hostList:

        try:
            answer = dns.resolver.query(host, 'A')
        except dns.resolver.NXDOMAIN:
            print("WARNING: Non existing hostname: "+host)
            continue
        except:
            print("WARNING: DNS Error: "+host)
            continue

        newIP=answer[0].address
        #modify short TTLs to 3 minutes
        newTTL=max(answer.ttl, defaultTTL);

        if (newIP in resolvedIPs):
            #If the resolved IP already exists in the dictionary, update the TTL and update time
            resolvedIPs[newIP].ttl=newTTL
            resolvedIPs[newIP].insertedAt=currentTime
        else:
            #If resolved IP is new, add to the dictionary
            newIPAttributes=IPAttributes()
            newIPAttributes.ttl=newTTL
            newIPAttributes.insertedAt=currentTime
            resolvedIPs[newIP]=newIPAttributes

    #check expired TTLs and remove from dictionary
    removeIPs=[IP for IP in resolvedIPs if resolvedIPs[IP].insertedAt+resolvedIPs[IP].ttl<=currentTime]
    for IP in removeIPs: del resolvedIPs[IP]
            
    #update the ACL on the router

    try:
        session_handle = ne.connect(RouterUser, RouterPassword, session_config)
    except:
        print("ERROR: Couldn't connect to "+ne.host_address)
    else:
        i=0
        commandList="conf t\n"
        commandList+="ip access-list extended "+aclName+"\n"
        for configureIP in resolvedIPs:
            # need some tricks to make teh ACL modification work correctly
            # 1. remove any occurrence of IP in the ACL
            commandList+="no deny ip any "+configureIP+" 0.0.0.0\n"
            # 2. remove the entry with the index to modify
            commandList+="no "+str(i+1)+"\n"
            # 3. modify the entry
            commandList+=str(i+1)+" deny ip any "+configureIP+" 0.0.0.0\n"
            i+=1
        # clear all entries at the end of the ACL
        while i<maxACLLines:
            commandList+="no "+str(i+1)+"\n"
            i+=1
        commandList+=str(maxACLLines+1)+" permit any any\n"

        ne_vty=VtyService(ne)

        try:
            ne_vty.open()
        except:
            print("ERROR: Couldn't connect to VtyService "+ne.host_address)
        else:
            cli_result=ne_vty.write(commandList)

            ne_vty.close()
            ne.disconnect()

    #print the ACL to screen for visual check
    # ------ START - remove this for production -------
    print("ip access-list extended "+aclName)

    i=0
    for printIP in resolvedIPs:
        print(str(i+1)+" deny ip any "+printIP+" 0.0.0.0")
        i+=1
    while i<maxACLLines:
        print("no "+str(i+1))
        i+=1
    print(str(maxACLLines+1)+" permit any any")
    # ------ END - remove this for production -------
    
    time.sleep(refreshInterval)
