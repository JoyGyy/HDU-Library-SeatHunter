import React, { useState, useEffect } from 'react'
import { View, Text, StyleSheet, TouchableOpacity, FlatList, Alert, TextInput, Modal, ActivityIndicator } from 'react-native'
import { getFriends, addFriend, deleteFriend, testFriendLogin } from '../api/client'

interface Friend {
  student_id: string
  name: string
  uid: string
}

export default function FriendsScreen() {
  const [friends, setFriends] = useState<Friend[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [sid, setSid] = useState('')
  const [pwd, setPwd] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => { loadFriends() }, [])

  const loadFriends = async () => {
    try {
      const resp = await getFriends()
      setFriends(resp.data.friends)
    } catch (e) { /* ignore */ }
  }

  const handleAdd = async () => {
    if (!sid || !pwd) { Alert.alert('提示', '请输入学号和密码'); return }
    setLoading(true)
    try {
      const resp = await addFriend(sid, pwd)
      if (resp.data.success) {
        Alert.alert('成功', `已添加: ${resp.data.name}`)
        setShowAdd(false); setSid(''); setPwd('')
        loadFriends()
      } else {
        Alert.alert('失败', resp.data.message)
      }
    } catch (e) {
      Alert.alert('错误', '添加失败')
    }
    setLoading(false)
  }

  const handleDelete = (friend: Friend) => {
    Alert.alert('确认', `删除好友 ${friend.name}？`, [
      { text: '取消' },
      {
        text: '删除', style: 'destructive', onPress: async () => {
          await deleteFriend(friend.student_id)
          loadFriends()
        },
      },
    ])
  }

  const handleTest = async (friend: Friend) => {
    try {
      const resp = await testFriendLogin(friend.student_id)
      Alert.alert(resp.data.success ? '成功' : '失败', resp.data.message)
    } catch (e) {
      Alert.alert('错误', '测试失败')
    }
  }

  const renderItem = ({ item }: { item: Friend }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.name}>{item.name}</Text>
        <Text style={styles.sid}>{item.student_id}</Text>
      </View>
      <Text style={styles.uid}>UID: {item.uid}</Text>
      <View style={styles.actions}>
        <TouchableOpacity style={styles.testBtn} onPress={() => handleTest(item)}>
          <Text style={styles.testBtnText}>测试登录</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.deleteBtn} onPress={() => handleDelete(item)}>
          <Text style={styles.deleteBtnText}>删除</Text>
        </TouchableOpacity>
      </View>
    </View>
  )

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>好友列表</Text>
        <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
          <Text style={styles.addBtnText}>+ 添加</Text>
        </TouchableOpacity>
      </View>
      <FlatList
        data={friends}
        renderItem={renderItem}
        keyExtractor={item => item.student_id}
        ListEmptyComponent={<Text style={styles.empty}>暂无好友</Text>}
      />

      <Modal visible={showAdd} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modal}>
            <Text style={styles.modalTitle}>添加好友</Text>
            <TextInput
              style={styles.input}
              placeholder="学号"
              value={sid}
              onChangeText={setSid}
              placeholderTextColor="#666"
            />
            <TextInput
              style={styles.input}
              placeholder="密码"
              value={pwd}
              onChangeText={setPwd}
              secureTextEntry
              placeholderTextColor="#666"
            />
            <View style={styles.modalActions}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowAdd(false)}>
                <Text style={styles.cancelBtnText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.confirmBtn} onPress={handleAdd} disabled={loading}>
                {loading
                  ? <ActivityIndicator color="#1e1e2e" />
                  : <Text style={styles.confirmBtnText}>添加</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1e1e2e', padding: 16 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  title: { fontSize: 20, fontWeight: 'bold', color: '#cdd6f4' },
  addBtn: { backgroundColor: '#89b4fa', borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8 },
  addBtnText: { color: '#1e1e2e', fontWeight: 'bold' },
  card: { backgroundColor: '#313244', borderRadius: 12, padding: 16, marginBottom: 12 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  name: { fontSize: 16, fontWeight: 'bold', color: '#cdd6f4' },
  sid: { fontSize: 14, color: '#a6adc8' },
  uid: { fontSize: 13, color: '#a6adc8', marginBottom: 12 },
  actions: { flexDirection: 'row', gap: 8 },
  testBtn: { backgroundColor: '#45475a', borderRadius: 6, paddingHorizontal: 12, paddingVertical: 6 },
  testBtnText: { color: '#89b4fa', fontSize: 13 },
  deleteBtn: { backgroundColor: '#45475a', borderRadius: 6, paddingHorizontal: 12, paddingVertical: 6 },
  deleteBtnText: { color: '#f38ba8', fontSize: 13 },
  empty: { color: '#a6adc8', textAlign: 'center', marginTop: 40, fontSize: 16 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'center', padding: 20 },
  modal: { backgroundColor: '#313244', borderRadius: 16, padding: 24 },
  modalTitle: { fontSize: 18, fontWeight: 'bold', color: '#cdd6f4', marginBottom: 16 },
  input: {
    height: 48, backgroundColor: '#1e1e2e', borderRadius: 8, paddingHorizontal: 16,
    color: '#cdd6f4', fontSize: 16, marginBottom: 12, borderWidth: 1, borderColor: '#45475a',
  },
  modalActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 12, marginTop: 8 },
  cancelBtn: { paddingHorizontal: 20, paddingVertical: 10 },
  cancelBtnText: { color: '#a6adc8', fontSize: 16 },
  confirmBtn: { backgroundColor: '#89b4fa', borderRadius: 8, paddingHorizontal: 20, paddingVertical: 10 },
  confirmBtnText: { color: '#1e1e2e', fontSize: 16, fontWeight: 'bold' },
})
