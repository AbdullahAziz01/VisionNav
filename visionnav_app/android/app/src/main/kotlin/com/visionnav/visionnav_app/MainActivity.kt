package com.visionnav.visionnav_app

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.io.FileNotFoundException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val settings = AtomicFile(File(noBackupFilesDir, "visionnav-settings"))
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "visionnav/settings")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "read" -> result.success(readSettings(settings))
                        "write" -> {
                            val json = requireNotNull(call.arguments as? String)
                            writeSettings(settings, json)
                            result.success(null)
                        }
                        else -> result.notImplemented()
                    }
                } catch (_: Exception) {
                    result.error("settings_storage", "Device settings storage failed.", null)
                }
            }
    }

    private fun settingsKey(create: Boolean): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "visionnav.settings.v1"
        val key = store.getKey(alias, null) as? SecretKey
        if (key != null) return key
        check(create)
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            .apply {
                init(KeyGenParameterSpec.Builder(
                    alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
                ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build())
            }.generateKey()
    }

    private fun readSettings(file: AtomicFile): String? {
        val bytes = try {
            file.readFully()
        } catch (_: FileNotFoundException) {
            return null
        }
        val ivSize = bytes.first().toInt() and 0xff
        check(ivSize in 12..16 && bytes.size > ivSize + 1)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, settingsKey(create = false),
            GCMParameterSpec(128, bytes.copyOfRange(1, ivSize + 1)))
        return cipher.doFinal(bytes, ivSize + 1, bytes.size - ivSize - 1).toString(Charsets.UTF_8)
    }

    private fun writeSettings(file: AtomicFile, json: String) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, settingsKey(create = true))
        val iv = cipher.iv
        val ciphertext = cipher.doFinal(json.toByteArray(Charsets.UTF_8))
        val stream = file.startWrite()
        try {
            stream.write(iv.size)
            stream.write(iv)
            stream.write(ciphertext)
            file.finishWrite(stream)
        } catch (error: Exception) {
            file.failWrite(stream)
            throw error
        }
    }
}
