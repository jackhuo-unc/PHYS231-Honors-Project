// using UnityEngine;
// using UnityEngine.InputSystem;

// public class DeviceDebug : MonoBehaviour
// {
//     void Start()
//     {
//         foreach (var d in InputSystem.devices)
//         {
//             Debug.Log($"Device: {d.name} ({d.layout}) - {d.description}");
//         }
//     }
// }
using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using UnityEngine;
using UnityEngine.XR;

public class JoystickToUdp : MonoBehaviour
{
    [Header("Network")]
    public string piIpAddress = "172.20.10.13";
    public int piPort = 5005;

    [Header("Control")]
    public float maxYawSpeed = 60f;
    public float stickDeadzone = 0.15f;
    public float sendRateHz = 30f;

    private UdpClient udpClient;
    private IPEndPoint remoteEndPoint;
    private float sendInterval;
    private float timeSinceLastSend;

    void Start()
    {
        udpClient = new UdpClient();
        remoteEndPoint = new IPEndPoint(IPAddress.Parse(piIpAddress), piPort);
        sendInterval = 1f / sendRateHz;
        Debug.Log($"JoystickToUdp -> {piIpAddress}:{piPort}");
    }

    void Update()
    {
        timeSinceLastSend += Time.deltaTime;
        if (timeSinceLastSend < sendInterval) return;
        timeSinceLastSend = 0f;

        // Find the right-hand controller
        var rightHandDevices = new List<InputDevice>();
        InputDevices.GetDevicesAtXRNode(XRNode.RightHand, rightHandDevices);

        Vector2 stickValue = Vector2.zero;

        if (rightHandDevices.Count > 0)
        {
            var device = rightHandDevices[0];
            if (device.TryGetFeatureValue(CommonUsages.primary2DAxis, out Vector2 axis))
            {
                stickValue = axis;
            }
        }

        if (stickValue.sqrMagnitude > 0.01f)
            Debug.Log($"Right stick: {stickValue}");

        float stickX = stickValue.x;
        if (Mathf.Abs(stickX) < stickDeadzone) stickX = 0f;

        float yawVelocity = stickX * maxYawSpeed;
        SendVelocityPacket(yawVelocity, 0f);
    }

    void SendVelocityPacket(float yaw, float pitch)
    {
        byte[] packet = new byte[12];
        packet[0] = 1;  // PACKET_TYPE_VELOCITY
        Buffer.BlockCopy(BitConverter.GetBytes(yaw), 0, packet, 4, 4);
        Buffer.BlockCopy(BitConverter.GetBytes(pitch), 0, packet, 8, 4);
        try
        {
            udpClient.Send(packet, packet.Length, remoteEndPoint);
        }
        catch (Exception e)
        {
            Debug.LogError($"UDP send failed: {e.Message}");
        }
    }

    void OnDestroy()
    {
        udpClient?.Close();
    }
}