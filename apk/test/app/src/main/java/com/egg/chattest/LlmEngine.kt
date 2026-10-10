package com.egg.chattest

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.io.File
import java.nio.FloatBuffer
import java.nio.LongBuffer
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * Native on-device inference for Qwen2.5-0.5B-Instruct (q4) on ONNX Runtime.
 *
 * Tokenization, the chat template and detokenization stay in JS (transformers.js);
 * this class owns the ORT session, the KV-cache feedback loop and sampling, so the
 * heavy matmuls never run inside the WebView's WASM sandbox. This is the fix for the
 * renderer death caused by loading a 483 MB model into WASM linear memory.
 *
 * Model facts (verified): plain graph, opset 14 + com.microsoft, MatMulNBits q4,
 * 24 layers, 2 KV heads, head_dim 64, vocab 151936. Inputs:
 *   input_ids, attention_mask, position_ids, past_key_values.{0..23}.{key,value}
 * Outputs: logits [1,S,vocab] + present.{0..23}.{key,value}
 */
class LlmEngine(modelFile: File) {

    interface Sink {
        fun onToken(id: Int)
        fun onDone()
        fun onError(message: String)
    }

    private val env: OrtEnvironment = OrtEnvironment.getEnvironment()
    private val session: OrtSession
    private val lock = ReentrantLock()

    private val layers = 24
    private val kvHeads = 2L
    private val headDim = 64L
    private val vocab = 151936

    private val kvIn = ArrayList<String>(layers * 2)
    private val outNames: Set<String>

    @Volatile private var cancelled = false

    init {
        val threads = Runtime.getRuntime().availableProcessors().coerceIn(2, 4)
        val opts = OrtSession.SessionOptions().apply {
            setIntraOpNumThreads(threads)
            setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
        }
        session = env.createSession(modelFile.absolutePath, opts)

        val outs = HashSet<String>()
        outs.add("logits")
        for (l in 0 until layers) {
            kvIn.add("past_key_values.$l.key")
            kvIn.add("past_key_values.$l.value")
            outs.add("present.$l.key")
            outs.add("present.$l.value")
        }
        outNames = outs
    }

    fun cancel() {
        cancelled = true
    }

    fun close() {
        try { session.close() } catch (_: Throwable) {}
    }

    /** Blocking. Runs on a background thread. One generation at a time. */
    fun generate(
        promptIds: IntArray,
        maxNew: Int,
        temperature: Float,
        topK: Int,
        topP: Float,
        repetitionPenalty: Float,
        eosIds: IntArray,
        sink: Sink
    ) = lock.withLock {
        cancelled = false
        try {
            loop(promptIds, maxNew, temperature, topK, topP, repetitionPenalty, eosIds.toSet(), sink)
        } catch (t: Throwable) {
            sink.onError(t.message ?: t.toString())
        }
    }

    private fun zeros(): OnnxTensor =
        OnnxTensor.createTensor(env, FloatBuffer.allocate(0), longArrayOf(1, kvHeads, 0, headDim))

    private fun longTensor(data: LongArray, shape: LongArray): OnnxTensor {
        val b = LongBuffer.allocate(data.size)
        b.put(data)
        b.rewind()
        return OnnxTensor.createTensor(env, b, shape)
    }

    /** FloatArray copy of the last position's logits row. */
    private fun lastRow(res: OrtSession.Result): FloatArray {
        val t = res.get("logits").get() as OnnxTensor
        val seq = t.info.shape[1].toInt()
        val fb = t.floatBuffer
        val out = FloatArray(vocab)
        fb.position((seq - 1) * vocab)
        fb.get(out)
        return out
    }

    private fun loop(
        promptIds: IntArray,
        maxNew: Int,
        temperature: Float,
        topK: Int,
        topP: Float,
        repetitionPenalty: Float,
        eos: Set<Int>,
        sink: Sink
    ) {
        // ---------- prefill ----------
        val seq = promptIds.size
        val prefillFeed = HashMap<String, OnnxTensor>()
        prefillFeed["input_ids"] =
            longTensor(LongArray(seq) { promptIds[it].toLong() }, longArrayOf(1, seq.toLong()))
        prefillFeed["attention_mask"] =
            longTensor(LongArray(seq) { 1L }, longArrayOf(1, seq.toLong()))
        prefillFeed["position_ids"] =
            longTensor(LongArray(seq) { it.toLong() }, longArrayOf(1, seq.toLong()))
        for (n in kvIn) prefillFeed[n] = zeros()
        val prefillRes = session.run(prefillFeed, outNames)
        for (t in prefillFeed.values) t.close()

        var logits = lastRow(prefillRes)
        var total = seq
        var prev: OrtSession.Result? = prefillRes

        // ---------- decode ----------
        val generated = ArrayList<Int>(maxNew)
        var produced = 0
        while (produced < maxNew && !cancelled) {
            val id = sample(logits, promptIds, generated, temperature, topK, topP, repetitionPenalty)
            generated.add(id)
            produced++
            if (id in eos) break
            sink.onToken(id)

            val p = prev ?: break
            val feed = HashMap<String, OnnxTensor>()
            feed["input_ids"] = longTensor(longArrayOf(id.toLong()), longArrayOf(1, 1))
            feed["attention_mask"] =
                longTensor(LongArray(total + 1) { 1L }, longArrayOf(1, (total + 1).toLong()))
            feed["position_ids"] = longTensor(longArrayOf(total.toLong()), longArrayOf(1, 1))
            for (n in kvIn) feed[n] = p.get(n).get() as OnnxTensor
            val res = session.run(feed, outNames)
            feed["input_ids"]!!.close()
            feed["attention_mask"]!!.close()
            feed["position_ids"]!!.close()
            logits = lastRow(res)
            p.close()
            prev = res
            total += 1
        }

        prev?.close()
        sink.onDone()
    }

    private fun sample(
        logits: FloatArray,
        prompt: IntArray,
        gen: List<Int>,
        temperature: Float,
        topK: Int,
        topP: Float,
        rep: Float
    ): Int {
        val n = logits.size

        if (rep != 1f) {
            val seen = HashSet<Int>(prompt.size + gen.size)
            for (t in prompt) seen.add(t)
            seen.addAll(gen)
            for (t in seen) {
                val v = logits[t]
                logits[t] = if (v > 0f) v / rep else v * rep
            }
        }

        if (temperature <= 0f) {
            var bi = 0
            var bv = -Float.MAX_VALUE
            for (i in 0 until n) if (logits[i] > bv) { bv = logits[i]; bi = i }
            return bi
        }
        for (i in 0 until n) logits[i] /= temperature

        val k = if (topK in 1 until n) topK else n
        val idx = Array(n) { it }
        idx.sortWith(Comparator<Int> { a, b -> logits[b].compareTo(logits[a]) })

        var m = -Float.MAX_VALUE
        for (i in 0 until k) if (logits[idx[i]] > m) m = logits[idx[i]]

        val probs = FloatArray(k)
        var sum = 0.0
        for (i in 0 until k) {
            val e = Math.exp((logits[idx[i]] - m).toDouble())
            probs[i] = e.toFloat()
            sum += e
        }
        var cum = 0.0
        var cut = k
        for (i in 0 until k) {
            probs[i] = (probs[i] / sum).toFloat()
            cum += probs[i]
            if (cum >= topP) { cut = i + 1; break }
        }
        var s2 = 0.0
        for (i in 0 until cut) s2 += probs[i]
        val r = Math.random() * s2
        var acc = 0.0
        var pick = cut - 1
        for (i in 0 until cut) {
            acc += probs[i]
            if (r <= acc) { pick = i; break }
        }
        return idx[pick]
    }
}
