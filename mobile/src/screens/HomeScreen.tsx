import React, { useEffect, useState } from 'react'
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
} from 'react-native'
import { getAuthStatus, login, setBaseURL } from '../api/client'

export default function HomeScreen() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [userName, setUserName] = useState('')
  const [serverURL, setServerURL] = useState('https://legwarmer-favorably-musty.ngrok-free.dev')
  const [studentId, setStudentId] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    checkStatus()
  }, [])

  const checkStatus = async () => {
    try {
      const resp = await getAuthStatus()
      setLoggedIn(resp.data.logged_in)
      setUserName(resp.data.name)
    } catch {
      // 后端未连接
    }
  }

  const handleLogin = async () => {
    setBaseURL(serverURL)
    setLoading(true)
    try {
      const resp = await login(studentId, password)
      if (resp.data.success) {
        setLoggedIn(true)
        setUserName(resp.data.name)
        Alert.alert('成功', `欢迎, ${resp.data.name}`)
      } else {
        Alert.alert('失败', resp.data.message)
      }
    } catch (err: any) {
      const detail = err?.message || String(err)
      Alert.alert('连接失败', `无法连接后端\n${detail}`)
    }
    setLoading(false)
  }

  if (!loggedIn) {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>HDU 图书馆抢座</Text>
        <TextInput
          style={styles.input}
          placeholder="后端地址"
          value={serverURL}
          onChangeText={setServerURL}
          placeholderTextColor="#666"
          autoCapitalize="none"
          autoCorrect={false}
        />
        <TextInput
          style={styles.input}
          placeholder="学号"
          value={studentId}
          onChangeText={setStudentId}
          placeholderTextColor="#666"
        />
        <TextInput
          style={styles.input}
          placeholder="密码"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholderTextColor="#666"
        />
        <TouchableOpacity
          style={styles.button}
          onPress={handleLogin}
          disabled={loading}
        >
          <Text style={styles.buttonText}>
            {loading ? '登录中...' : '登录'}
          </Text>
        </TouchableOpacity>
      </View>
    )
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>HDU 图书馆抢座</Text>
      <Text style={styles.subtitle}>已登录: {userName}</Text>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#1e1e2e',
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#cdd6f4',
    marginBottom: 20,
  },
  subtitle: {
    fontSize: 16,
    color: '#a6adc8',
  },
  input: {
    width: '100%',
    height: 48,
    backgroundColor: '#313244',
    borderRadius: 8,
    paddingHorizontal: 16,
    color: '#cdd6f4',
    fontSize: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#45475a',
  },
  button: {
    width: '100%',
    height: 48,
    backgroundColor: '#89b4fa',
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8,
  },
  buttonText: {
    color: '#1e1e2e',
    fontSize: 16,
    fontWeight: 'bold',
  },
})
