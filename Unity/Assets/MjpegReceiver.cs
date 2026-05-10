using System;
using System.Collections;
using System.IO;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

public class MjpegReceiver : MonoBehaviour
{
    [Header("Stream")]
    public string streamUrl = "http://172.20.10.13:8080/stream";

    [Header("Display")]
    public Renderer targetRenderer;   // assign this quad's Renderer

    private Texture2D texture;
    private byte[] latestFrame;
    private readonly object frameLock = new object();
    private CancellationTokenSource cts;
    private Task readerTask;

    void Start()
    {
        if (targetRenderer == null) targetRenderer = GetComponent<Renderer>();

        // Start with a tiny placeholder texture; will be resized on first frame
        texture = new Texture2D(2, 2, TextureFormat.RGB24, false);
        targetRenderer.material.mainTexture = texture;

        cts = new CancellationTokenSource();
        readerTask = Task.Run(() => ReadStream(cts.Token));
    }

    async Task ReadStream(CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            try
            {
                using (var client = new HttpClient())
                {
                    client.Timeout = TimeSpan.FromSeconds(5);
                    using (var stream = await client.GetStreamAsync(streamUrl))
                    {
                        await ReadMjpegStream(stream, token);
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"MJPEG: {e.Message}, reconnecting in 1s");
                try { await Task.Delay(1000, token); } catch { }
            }
        }
    }

    async Task ReadMjpegStream(Stream stream, CancellationToken token)
    {
        // JPEG SOI = FF D8, EOI = FF D9. We scan the byte stream for these.
        byte[] buffer = new byte[64 * 1024];
        var ms = new MemoryStream();
        int prev = -1;
        bool inJpeg = false;

        while (!token.IsCancellationRequested)
        {
            int read = await stream.ReadAsync(buffer, 0, buffer.Length, token);
            if (read <= 0) return;

            for (int i = 0; i < read; i++)
            {
                byte b = buffer[i];
                if (!inJpeg)
                {
                    if (prev == 0xFF && b == 0xD8)
                    {
                        ms.SetLength(0);
                        ms.WriteByte(0xFF);
                        ms.WriteByte(0xD8);
                        inJpeg = true;
                    }
                }
                else
                {
                    ms.WriteByte(b);
                    if (prev == 0xFF && b == 0xD9)
                    {
                        // Complete JPEG
                        byte[] frame = ms.ToArray();
                        lock (frameLock) { latestFrame = frame; }
                        inJpeg = false;
                        ms.SetLength(0);
                    }
                }
                prev = b;
            }
        }
    }

    void Update()
    {
        byte[] frame = null;
        lock (frameLock)
        {
            if (latestFrame != null)
            {
                frame = latestFrame;
                latestFrame = null;
            }
        }

        if (frame != null)
        {
            // LoadImage auto-resizes the texture
            texture.LoadImage(frame);
        }
    }

    void OnDestroy()
    {
        cts?.Cancel();
    }
}