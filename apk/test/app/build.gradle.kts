plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.egg.chattest"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.egg.chattest"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    // Keep the self-hosted model + ORT wasm binaries uncompressed in the APK so the
    // WebView can stream them directly (aapt compression of a 786MB .onnx is unusable).
    androidResources {
        noCompress += listOf("onnx", "wasm", "mjs", "json")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.webkit:webkit:1.11.0")

    // Native inference. Full AAR ("all types and operators") -> ships the
    // com.microsoft::MatMulNBits q4 kernel this model needs. Do NOT swap for a
    // stripped onnxruntime-mobile build unless MatMulNBits is in its ops config.
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.20.0")
}
