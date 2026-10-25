#include <iostream>
#include <vector>
#include <queue>

int main() {
    int N, K;
    std::cin >> N >> K;
    
    std::vector<long long> arr(N);
    for (int i = 0; i < N; ++i) {
        std::cin >> arr[i];
    }
    
    std::priority_queue<long long, std::vector<long long>, std::greater<long long>> minHeap;
    long long sum = 0, maxSum = -1e18;
    
    for (int i = 0; i < N; ++i) {
        sum += arr[i];
        minHeap.push(arr[i]);
        
        if (i >= K) {
            sum -= minHeap.top();
            minHeap.pop();
        }
        
        if (i >= K - 1) {
            maxSum = std::max(maxSum, sum);
        }
    }
    
    // Fix: Ensure maxSum is updated with the sum of the entire array if K >= N
    if (K >= N) {
        maxSum = std::accumulate(arr.begin(), arr.end(), 0LL);
    }
    
    std::cout << maxSum << std::endl;
    return 0;
}