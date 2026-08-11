package com.amaksoft.notifrelay.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface SeenChannelDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(channel: SeenChannelEntity)

    @Query("SELECT * FROM seen_channels ORDER BY lastSeenMillis DESC")
    suspend fun getAll(): List<SeenChannelEntity>

    @Query("SELECT * FROM seen_channels ORDER BY lastSeenMillis DESC")
    fun observeAll(): Flow<List<SeenChannelEntity>>

    @Query("SELECT * FROM seen_channels WHERE packageName = :packageName ORDER BY lastSeenMillis DESC")
    suspend fun getForPackage(packageName: String): List<SeenChannelEntity>
}
