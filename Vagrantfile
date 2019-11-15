# -*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

 if Vagrant.has_plugin?("vagrant-hostmanager")
     config.hostmanager.enabled = true
     config.hostmanager.manage_host = true
 end

 # Vagrant can share the source directory using rsync, NFS, or SSHFS (with the vagrant-sshfs
 # plugin). By default it rsyncs the current working directory to /vagrant.
 #
 # If you would prefer to use NFS to share the directory uncomment this and configure NFS
 # config.vm.synced_folder ".", "/vagrant", type: "nfs", nfs_version: 4, nfs_udp: false
 config.vm.synced_folder ".", "/vagrant", disabled: true

 # To cache update packages (which is helpful if frequently doing `vagrant destroy && vagrant up`)
 # you can create a local directory and share it to the guest's DNF cache. The directory needs to
 # exist, so create it before you uncomment the line below.
 #
 # config.vm.synced_folder ".dnf-cache", "/var/cache/dnf", type: "sshfs", sshfs_opts_append: "-o nonempty"

 # Comment this line if you would like to disable the automatic update during provisioning
 # config.vm.provision "shell", inline: "sudo dnf upgrade -y"

 # bootstrap and run with ansible

 config.vm.define "gitlab" do |gitlab|
    gitlab.vm.host_name = "gitlab"
    gitlab.vm.box_url = "https://cloud.centos.org/centos/7/vagrant/x86_64/images/CentOS-7-x86_64-Vagrant-1907_01.Libvirt.box"
    gitlab.vm.box = "centos7-1907-libvirt"
    gitlab.vm.box_download_checksum = "10907f19d5ff7d5bab5bef414bdb7305bbff39502001bd36b82ef3a9afc62910"
    gitlab.vm.box_download_checksum_type = "sha256"

    # Expose Gitlab on port 8443 for the web UI and SSH on 2222
    gitlab.vm.network "forwarded_port", guest: 443, host: 8443, host_ip: "0.0.0.0"
    gitlab.vm.network "forwarded_port", guest: 2222, host: 2222, host_ip: "0.0.0.0"

    gitlab.vm.provision "shell", inline: "sudo yum update -y"
    gitlab.vm.provision "ansible" do |ansible|
        ansible.playbook = "devel/ansible/gitlab-playbook.yml"
    end

    gitlab.vm.provider :libvirt do |domain|
        # Season to taste
        domain.cpus = 4
        domain.graphics_type = "spice"
        domain.memory = 4096
        domain.video_type = "qxl"
        # domain.volume_cache = "unsafe"
    end
 end

 config.vm.define "pw" do |pw|
    pw.vm.box = "fedora/30-cloud-base"
    pw.vm.synced_folder ".", "/home/vagrant/patchlab", type: "sshfs"

    # Forward traffic on the host to the Django development server on the guest
    pw.vm.network "forwarded_port", guest: 8000, host: 8000, host_ip: "0.0.0.0"
    # The RabbitMQ admin console, http://localhost:15672 (username "guest", password "guest")
    pw.vm.network "forwarded_port", guest: 15672, host: 15672, host_ip: "0.0.0.0"
    pw.vm.host_name = "patchwork"
    pw.vm.provision "shell", inline: "sudo dnf update -y && sudo dnf -y install python3-libselinux"
    pw.vm.provision "ansible" do |ansible|
        ansible.playbook = "devel/ansible/patchwork-playbook.yml"
    end

    pw.vm.provider :libvirt do |domain|
        # Season to taste
        domain.cpus = 4
        domain.graphics_type = "spice"
        domain.memory = 2048
        domain.video_type = "qxl"

        # Uncomment the following line if you would like to enable libvirt's unsafe cache
        # mode. It is called unsafe for a reason, as it causes the virtual host to ignore all
        # fsync() calls from the guest. Only do this if you are comfortable with the possibility of
        # your development guest becoming corrupted (in which case you should only need to do a
        # vagrant destroy and vagrant up to get a new one).
        #
        # domain.volume_cache = "unsafe"
    end
 end
end
