# Stop k3s service and any background processes
sudo systemctl stop k3s
sudo systemctl disable k3s 2>/dev/null || true

# Kill any leftover container shims and k3s processes
sudo pkill -f containerd-shim
sudo pkill -f k3s
sudo pkill -f containerd

# Stop containerd-related services if running
sudo systemctl list-units | grep containerd | awk '{print $1}' | xargs -r sudo systemctl stop

# Run the built-in k3s killall helper if it exists
if [ -x /usr/bin/k3s-killall.sh ]; then
  sudo /usr/bin/k3s-killall.sh
elif [ -x /usr/local/bin/k3s-killall.sh ]; then
  sudo /usr/local/bin/k3s-killall.sh
fi

# Remove leftover network interfaces from CNI or flannel
for iface in cni0 flannel.1 docker0; do
  sudo ip link delete "$iface" 2>/dev/null || true
done

# Remove random bridge and veth interfaces (created by CNI)
for iface in $(ip -o link show | awk -F': ' '/(veth|br-)/{print $2}'); do
  sudo ip link delete "$iface" 2>/dev/null || true
done

# Remove any leftover container network namespaces
for ns in $(sudo ip netns list | awk '{print $1}'); do
  [[ "$ns" == cni-* ]] && sudo ip netns delete "$ns" || true
done

# Remove all residual data directories from k3s and containerd
sudo rm -rf /var/lib/rancher/
sudo rm -rf /var/lib/cni/
sudo rm -rf /etc/cni/
sudo rm -rf /run/flannel/
sudo rm -rf /var/lib/containerd/
sudo rm -rf /opt/cni/
sudo rm -rf /etc/rancher/
sudo rm -rf /run/k3s/

# Reload networking services to restore clean state
sudo systemctl restart systemd-networkd 2>/dev/null || sudo systemctl restart NetworkManager

echo "✅ Local Kubernetes (k3s) environment fully cleaned."
