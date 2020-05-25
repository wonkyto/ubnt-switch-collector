# ubnt-switch-collector
I recently purchased a Ubiquiti Unifi USW-16-POE switch. Unfortunately, unlike the Gen 1 switches it does not have adequate SNMP support to collect interface metrics. 

So I wrote a small interface metric collector in python that could connect to the switch, collect the metrics, and then send to an influxDB endpoint.
## Docker
Development has been done using docker to facilitate a standard environment.
### Building the docker image
The docker image can be built in the following way:
```bash
make build
```
You'll want to build the image when you have finished development, or if you make any changes to the Dockerfile including python dependencies
### Testing the script
During development it is time consuming to build a new container, so you can simply mount the script into the existing container for testing. The python script can be tested in the following way:
```bash
make test
```
### Linting the script
During development you can run flake8 on the script:
```bash
make flake8
```

### Running the script
Once you have finished development, build the docker image, and run it using:
```bash
make run
```

## Configuration
The container requires both a configuration file to be present, and also an ssh private key which gives access to the admin user on your Unifi devices.
### config/config.yaml
Here we define the following:
 * InfluxDb: Your InfluxDB endpoint and db
 * Switch: The name, ip/hostname and user credentials of your Unifi switch
 * InterfaceDesc: Some human descriptions of your ports (these might be on your Unifi Controller, but I didn't bother to figure out how to extract)
### key/id_rsa
This should be the private key which gives access to your admin user on your Unifi devices
