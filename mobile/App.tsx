import React from 'react'
import { NavigationContainer } from '@react-navigation/native'
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs'
import HomeScreen from './src/screens/HomeScreen'

const Tab = createBottomTabNavigator()

export default function App() {
  return (
    <NavigationContainer>
      <Tab.Navigator
        screenOptions={{
          headerShown: false,
          tabBarStyle: {
            backgroundColor: '#1e1e2e',
            borderTopColor: '#45475a',
          },
          tabBarActiveTintColor: '#89b4fa',
          tabBarInactiveTintColor: '#a6adc8',
        }}
      >
        <Tab.Screen name="首页" component={HomeScreen} />
      </Tab.Navigator>
    </NavigationContainer>
  )
}
